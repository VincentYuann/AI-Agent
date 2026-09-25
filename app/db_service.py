import asyncio
import concurrent.futures
import logging
import re
import time
from typing import Optional, Dict, Any, Set
import httpx
import jwt

from .config import settings
from .portfolio_service import invalidate_portfolio_cache

logger = logging.getLogger(__name__)

# Allowed public tables for portfolio administrative management
ALLOWED_TABLES: Set[str] = {
    "profile",
    "projects",
    "experience",
    "philosophy_pillars",
    "resume_latex",
}

# Strictly forbidden SQL keywords and patterns for security
FORBIDDEN_KEYWORDS = [
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bCREATE\b",
    r"\bREPLACE\b",
    r"\bEXECUTE\b",
    r"\bCOPY\b",
    r"\bVACUUM\b",
    r"\bREINDEX\b",
    r"\bSET\s+ROLE\b",
    r"\bSET\s+SESSION\b",
]

# Forbidden schema and system table patterns
FORBIDDEN_SCHEMAS = [
    r"\bauth\.",
    r"\bstorage\.",
    r"\bvault\.",
    r"\bextensions\.",
    r"\bpg_catalog\.",
    r"\bpg_",
    r"\binformation_schema\.",
    r"\bcontact_rate_limits\b",
]


# SQL reserved keywords and clause identifiers that should not be parsed as table names
SQL_RESERVED_WORDS: Set[str] = {
    "set", "select", "where", "values", "from", "join", "into", "update",
    "default", "returning", "on", "conflict", "do", "nothing", "all",
    "distinct", "only", "null", "case", "when", "then", "else", "end",
    "order", "group", "by", "having", "limit", "offset", "table", "as",
}


def validate_safe_sql(sql: str) -> Optional[str]:
    """
    Validates that the provided SQL query satisfies security and safety rules.
    Returns None if valid, or an error string describing the violation.
    """
    if not sql or not sql.strip():
        return "SQL query cannot be empty."

    cleaned_sql = sql.strip()

    if len(cleaned_sql) > 50000:
        return "SQL query exceeds maximum allowed length (50,000 characters)."

    # 1. Check for forbidden DDL / admin keywords
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, cleaned_sql, re.IGNORECASE):
            keyword = pattern.replace(r"\b", "").strip()
            return f"Security violation: The SQL statement contains forbidden command '{keyword}'."

    # 2. Check for forbidden schemas and internal tables
    for pattern in FORBIDDEN_SCHEMAS:
        if re.search(pattern, cleaned_sql, re.IGNORECASE):
            return "Security violation: Queries referencing system, auth, or internal tables are blocked."

    # 3. Prevent unconditioned destructive DELETE statements
    delete_matches = re.finditer(
        r"\bDELETE\s+FROM\s+(?:\"?([a-zA-Z0-9_]+)\"?\s*\.\s*)?\"?([a-zA-Z0-9_]+)\"?",
        cleaned_sql,
        re.IGNORECASE,
    )
    for m in delete_matches:
        tbl = (m.group(2) or m.group(1)).lower()
        start_idx = m.end()
        end_idx = cleaned_sql.find(";", start_idx)
        clause = cleaned_sql[start_idx:end_idx] if end_idx != -1 else cleaned_sql[start_idx:]
        if not re.search(r"\bWHERE\b", clause, re.IGNORECASE):
            return f"Safety guardrail: Unbounded DELETE on table '{tbl}' without a WHERE clause is strictly prohibited."

    # 4. Verify that table operations only target allowed tables
    target_tables = set()

    # Match FROM, INTO, JOIN targets (with optional schema qualification and quotes)
    for m in re.finditer(
        r"\b(?:FROM|INTO|JOIN)\s+(?:\"?([a-zA-Z0-9_]+)\"?\s*\.\s*)?\"?([a-zA-Z0-9_]+)\"?",
        cleaned_sql,
        re.IGNORECASE,
    ):
        tbl = (m.group(2) or m.group(1)).lower()
        if tbl not in SQL_RESERVED_WORDS:
            target_tables.add(tbl)

    # Match UPDATE targets (excluding DO UPDATE in ON CONFLICT upsert clauses)
    for m in re.finditer(
        r"(?<!\bDO\s)\bUPDATE\s+(?:ONLY\s+)?(?:\"?([a-zA-Z0-9_]+)\"?\s*\.\s*)?\"?([a-zA-Z0-9_]+)\"?",
        cleaned_sql,
        re.IGNORECASE,
    ):
        tbl = (m.group(2) or m.group(1)).lower()
        if tbl not in SQL_RESERVED_WORDS:
            target_tables.add(tbl)

    for clean_target in target_tables:
        if clean_target not in ALLOWED_TABLES:
            return f"Access restricted: Table '{clean_target}' is not in the allowed portfolio tables whitelist ({', '.join(sorted(ALLOWED_TABLES))})."

    return None


def generate_admin_jwt(user_token: Optional[str] = None) -> str:
    """
    Returns an authorized admin token.
    If an existing user token is provided and valid, it is used.
    Otherwise, generates a short-lived, signed admin JWT using the server's SUPABASE_JWT_SECRET.
    """
    if user_token and user_token.strip():
        return user_token.strip()

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

    token = generate_admin_jwt(admin_token)

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

                # Check if query was a mutation (INSERT, UPDATE, DELETE)
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
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(execute_supabase_sql_async(sql, admin_token))).result()
    return asyncio.run(execute_supabase_sql_async(sql, admin_token))
