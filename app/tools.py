import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

from .config import load_prompt_file
from .portfolio_service import get_portfolio_context, get_live_resume_context
from .db_service import execute_supabase_sql

logger = logging.getLogger(__name__)

# Resolve ASSETS_DIR using pathlib
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
if not ASSETS_DIR.exists():
    ASSETS_DIR = Path(__file__).resolve().parent / "assets"


# -------------------------------------------------------------
# 1. LOCAL ASSET LOADERS (Cached in memory)
# -------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_resume_text() -> str:
    """Extract and cache resume text using PdfReader."""
    resume_path = ASSETS_DIR / "Vincent_Yuan_Resume.pdf"
    if not resume_path.exists():
        return "Resume document not found."
    reader = PdfReader(str(resume_path))
    return "\n".join([page.extract_text() or "" for page in reader.pages])


# -------------------------------------------------------------
# 2. TOOL EXECUTION FUNCTIONS
# -------------------------------------------------------------
def get_vincent_info() -> list[dict]:
    """Returns complete real-time information about Vincent Yuan from portfolio database (cached on server)."""
    text = get_portfolio_context()
    return [{"type": "text", "text": text}]


def get_resume() -> list[dict]:
    """Returns Vincent Yuan's live resume text from Supabase public.resume_latex (with local PDF fallback)."""
    text = get_live_resume_context(fallback_fn=_load_resume_text)
    return [{"type": "text", "text": text}]






def execute_supabase_sql_action(sql: str, explanation: str = "") -> list[dict]:
    """
    ADMIN-ONLY tool: Executes a validated, safe SQL query against the Supabase database.
    Invalidates the server-side cache upon successful mutation and triggers
    frontend Supabase Realtime synchronization.
    """
    logger.info(f"Admin executing Supabase SQL ({explanation}):\n{sql}")
    res = execute_supabase_sql(sql)

    if res.get("status") == "success":
        rows = res.get("rows_affected", 0)
        data = res.get("data")
        msg = f"SUCCESS: SQL query executed successfully on Supabase PostgreSQL. Records returned/affected: {rows}."
        if data:
            msg += f"\nDatabase Result:\n{json.dumps(data, indent=2, default=str)}"
        return [{"type": "text", "text": msg}]
    else:
        err_msg = res.get("message", "Unknown database execution error.")
        err_type = res.get("error_type", "ERROR")
        return [{"type": "text", "text": f"{err_type}: Failed to execute SQL query on Supabase: {err_msg}"}]


# -------------------------------------------------------------
# 3. TOOL SCHEMAS & REGISTRY
# -------------------------------------------------------------
get_vincent_info_tool = {
    "type": "function",
    "name": "get_vincent_info",
    "description": (
        "Fetches comprehensive, authoritative information about Vincent Yuan directly from his portfolio database. "
        "Includes his professional bio, technical capabilities, projects, work experience, engineering philosophy, "
        "origin story, and personal hobbies. Call this tool when answering questions about Vincent Yuan, his projects, "
        "experience, skills, or portfolio if not already present in the conversation context."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

get_resume_tool = {
    "type": "function",
    "name": "get_resume",
    "description": "Returns Vincent Yuan's resume text. Call this tool when answering questions about Vincent's formal resume document.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

execute_supabase_sql_tool = {
    "type": "function",
    "name": "execute_supabase_sql",
    "description": load_prompt_file("supabase_sql_tool_description.md"),
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "The PostgreSQL SQL statement to execute. Must be safe, valid SQL using dollar-quoting ($$...$$) for string literals.",
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation of what this SQL statement does, which table it modifies, and the semantic rationale.",
            },
        },
        "required": ["sql", "explanation"],
    },
}

# Built-in Gemini tools
google_search_tool = {"type": "google_search"}
url_context_tool = {"type": "url_context"}

# Base tools available to all users (admin and guests)
BASE_TOOLS_SCHEMA = [google_search_tool, url_context_tool, get_vincent_info_tool, get_resume_tool]

TOOL_FUNCTIONS = {
    "get_vincent_info": get_vincent_info,
    "get_resume": get_resume,
    "execute_supabase_sql": execute_supabase_sql_action,
}


def get_agent_tools(is_admin: bool = False) -> List[Dict[str, Any]]:
    """
    Returns the tools for the portfolio assistant.
    Administrative database tools are strictly restricted to verified administrators.
    """
    tools = list(BASE_TOOLS_SCHEMA)
    if is_admin:
        tools.append(execute_supabase_sql_tool)
    return tools
