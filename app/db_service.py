import asyncio
import concurrent.futures
import logging
import time
from typing import Optional, Dict, Any, Set
import httpx
import jwt

import sqlglot
from sqlglot import exp

from .config import settings
from .portfolio_service import invalidate_portfolio_cache
from .security import admin_token_context

logger = logging.getLogger(__name__)

# Allowed public tables for portfolio administrative management
ALLOWED_TABLES: Set[str] = {
    "profile",
    "projects",
    "experience",
    "philosophy_pillars",
    "resume_latex",
}

ALLOWED_SCHEMAS: Set[str] = {"public", ""}

FORBIDDEN_COMMANDS = {
    exp.Drop: "DROP",
    exp.Alter: "ALTER",
    exp.TruncateTable: "TRUNCATE",
    exp.Create: "CREATE",
    exp.Grant: "GRANT",
    exp.Revoke: "REVOKE",
}


def validate_safe_sql(sql: str) -> Optional[str]:
    """
    Validates that the provided SQL query satisfies security and safety rules
    using an AST parser (sqlglot) instead of brittle regexes.
    Returns None if valid, or an error string describing the violation.
    """
    if not sql or not sql.strip():
        return "SQL query cannot be empty."

    cleaned_sql = sql.strip()
    if len(cleaned_sql) > 50000:
        return "SQL query exceeds maximum allowed length (50,000 characters)."

    try:
        statements = sqlglot.parse(cleaned_sql, read="postgres")
    except Exception as e:
        return f"SQL parsing error: {e}"

    if not statements or all(s is None for s in statements):
        return "SQL query contains no valid statements."

    for stmt in statements:
        if stmt is None:
            continue

        # 1. Block explicitly forbidden DDL / admin commands
        for cls, name in FORBIDDEN_COMMANDS.items():
            if isinstance(stmt, cls) or stmt.find(cls):
                return f"Security violation: The SQL statement contains forbidden command '{name}'."

        # 2. Block procedural commands (DO $$ ... $$), COPY, and raw administrative commands
        if isinstance(stmt, exp.Command) or stmt.find(exp.Command):
            return "Security violation: Procedural blocks, raw commands, and execution wrappers are prohibited."

        if isinstance(stmt, exp.Copy) or stmt.find(exp.Copy):
            return "Security violation: COPY statements are prohibited."

        # 3. Whitelist: Statement must be SELECT, INSERT, UPDATE, or DELETE
        if not isinstance(stmt, (exp.Select, exp.Insert, exp.Update, exp.Delete)):
            return f"Security violation: Statement type '{stmt.key.upper()}' is not permitted. Only SELECT, INSERT, UPDATE, and DELETE are allowed."

        # 4. Block unconditioned destructive DELETE statements
        for del_node in stmt.find_all(exp.Delete):
            if not del_node.args.get("where"):
                tbl = del_node.this.name if del_node.this else "unknown"
                return f"Safety guardrail: Unbounded DELETE on table '{tbl}' without a WHERE clause is strictly prohibited."

        # 5. Check schemas and ensure query targets at least one allowed portfolio table
        tbl_nodes = list(stmt.find_all(exp.Table))
        if not tbl_nodes:
            # Blocks table-less system function exploitation like SELECT pg_read_file(...)
            return "Security violation: Query must target an explicit allowed portfolio table."

        for tbl_node in tbl_nodes:
            schema = (tbl_node.db or "").lower()
            table = tbl_node.name.lower()

            if schema and schema not in ALLOWED_SCHEMAS:
                return "Security violation: Queries referencing system, auth, or internal tables are blocked."

            if table and table not in ALLOWED_TABLES:
                if table in {"contact_rate_limits"}:
                    return "Security violation: Queries referencing system, auth, or internal tables are blocked."
                return f"Access restricted: Table '{table}' is not in the allowed portfolio tables whitelist ({', '.join(sorted(ALLOWED_TABLES))})."

    return None


def get_admin_bearer_token(admin_token: Optional[str] = None) -> str:
    """
    Retrieves an authorized admin bearer token for Supabase PostgREST RPC.
    
    1. Primary (Production): Uses the active admin user's verified bearer token
       propagated from the incoming HTTP request context.
    2. Explicit Fallback (Tests / CLI): If running outside an active HTTP request
       (e.g., during automated pytest runs or standalone CLI scripts), generates a
       short-lived server-signed token using SUPABASE_JWT_SECRET.
    """
    # 1. Check for token passed explicitly or active in request context
    active_token = admin_token or admin_token_context.get()
    if active_token and active_token.strip():
        return active_token.strip()

    # 2. Explicit Fallback for automated test suites or CLI maintenance scripts
    logger.debug("[DB AUTH] No active request bearer token found. Generating signed server token for test/CLI execution.")
    admin_email = settings.admin_emails_list[0] if settings.admin_emails_list else "vincentyuan1020@gmail.com"
    payload = {
        "sub": "ai-agent-admin-session",
        "email": admin_email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 180,  # 3-minute validity
    }
    secret = settings.SUPABASE_JWT_SECRET.get_secret_value()
    return jwt.encode(payload, secret, algorithm="HS256")


# Backward compatibility alias
generate_admin_jwt = get_admin_bearer_token


async def execute_supabase_sql_async(sql: str, admin_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Asynchronously executes SQL via the Supabase PostgREST RPC function 'execute_admin_sql'.
    Validates query safety, authenticates via Supabase Auth JWT, and invalidates
    server-side cache upon successful mutation.
    """
    validation_error = validate_safe_sql(sql)
    if validation_error:
        logger.warning(f"SQL validation rejected query: {validation_error}")
        return {
            "status": "error",
            "error_type": "VALIDATION_ERROR",
            "message": validation_error,
        }

    supabase_url = (settings.SUPABASE_URL or "").rstrip("/")
    if not supabase_url:
        return {
            "status": "error",
            "error_type": "CONFIGURATION_ERROR",
            "message": "SUPABASE_URL is not configured on the server.",
        }

    anon_key = settings.SUPABASE_ANON_KEY.get_secret_value() if settings.SUPABASE_ANON_KEY else ""
    if not anon_key:
        return {
            "status": "error",
            "error_type": "CONFIGURATION_ERROR",
            "message": "SUPABASE_ANON_KEY is not configured on the server.",
        }

    token = get_admin_bearer_token(admin_token)

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    rpc_url = f"{supabase_url}/rest/v1/rpc/execute_admin_sql"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(rpc_url, headers=headers, json={"query": sql})

            if res.status_code in (200, 201):
                payload = res.json()
                if isinstance(payload, dict) and payload.get("status") == "error":
                    error_msg = payload.get("message", "PostgreSQL query execution failed.")
                    logger.error(f"Supabase RPC execution error: {error_msg}")
                    return {
                        "status": "error",
                        "error_type": "POSTGRES_ERROR",
                        "message": error_msg,
                    }

                # Check if query was a mutation (INSERT, UPDATE, DELETE) using AST
                try:
                    parsed_stmts = sqlglot.parse(sql, read="postgres")
                    is_mutation = any(isinstance(s, (exp.Insert, exp.Update, exp.Delete)) for s in parsed_stmts if s)
                except Exception:
                    upper_sql = sql.strip().upper()
                    is_mutation = any(upper_sql.startswith(cmd) or f" {cmd} " in upper_sql for cmd in ["INSERT", "UPDATE", "DELETE"])

                if is_mutation:
                    logger.info("Database mutation detected. Invalidating server portfolio RAM cache...")
                    invalidate_portfolio_cache()

                logger.info("Supabase SQL executed successfully via RPC.")
                return {
                    "status": "success",
                    "data": payload,
                    "message": "Query executed successfully on Supabase PostgreSQL.",
                }
            else:
                error_body = res.text
                try:
                    err_json = res.json()
                    error_msg = err_json.get("message") or err_json.get("error") or error_body
                except Exception:
                    error_msg = error_body
                logger.error(f"Supabase API returned error ({res.status_code}): {error_msg}")
                return {
                    "status": "error",
                    "error_type": "HTTP_ERROR",
                    "status_code": res.status_code,
                    "message": error_msg,
                }
    except Exception as e:
        logger.error(f"Exception executing Supabase SQL: {e}", exc_info=True)
        return {
            "status": "error",
            "error_type": "NETWORK_OR_TIMEOUT_ERROR",
            "message": str(e),
        }


def execute_supabase_sql(sql: str, admin_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Thread-safe synchronous bridge for execute_supabase_sql_async.
    Supports execution inside or outside existing asyncio event loops.
    """
    # Capture the active request context token in the calling thread before thread delegation
    resolved_token = admin_token or admin_token_context.get()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(execute_supabase_sql_async(sql, resolved_token))).result()
    return asyncio.run(execute_supabase_sql_async(sql, resolved_token))
