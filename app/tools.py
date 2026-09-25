import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

from .portfolio_service import get_portfolio_context
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
    """Returns the text content of Vincent Yuan's resume."""
    return [{"type": "text", "text": _load_resume_text()}]


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
    "description": (
        "ADMIN-ONLY TOOL: Executes a safe PostgreSQL SQL statement directly against Vincent's Supabase database to add, update, or edit portfolio tables.\n\n"
        "TABLE SCHEMAS & COLUMN TYPES:\n"
        "1. public.profile (Single row, id = 1):\n"
        "   - id: integer (always 1)\n"
        "   - name, headline, tagline, email, github, linkedin, role: text\n"
        "   - capability_pillars, hobbies, hanko_card, origin_story: jsonb\n"
        "   - updated_at: timestamp with time zone (set to NOW())\n"
        "2. public.projects:\n"
        "   - id: text (primary key slug e.g. 'ai-agent-copilot')\n"
        "   - title: text (e.g. 'AI Agent Copilot')\n"
        "   - subtitle: text\n"
        "   - category: text\n"
        "   - description: text\n"
        "   - overview: text\n"
        "   - tech_stacks: text[] (use ARRAY['tag1', 'tag2']::text[])\n"
        "   - bullets: text[] (use ARRAY['bullet 1', 'bullet 2']::text[])\n"
        "   - github_link, live_link, badge, image: text\n"
        "   - kanji: text (single thematic Japanese kanji, e.g. '創', '智', '基', '迅', '墨')\n"
        "   - is_featured: boolean\n"
        "   - is_active: boolean\n"
        "   - status_label: text (e.g. 'ACTIVE / 稼働中', 'COMPLETED / 完了')\n"
        "   - start_date, end_date: text (e.g. 'September 2025')\n"
        "   - display_order: integer\n"
        "   - updated_at: timestamp with time zone (set to NOW())\n"
        "3. public.experience:\n"
        "   - id: uuid (primary key, use gen_random_uuid() for new rows)\n"
        "   - title: text (e.g. 'Staff AI Engineer')\n"
        "   - company: text (e.g. 'Google DeepMind')\n"
        "   - location: text (e.g. 'Mountain View, CA')\n"
        "   - start_date, end_date: text (e.g. 'March 2025', 'Present')\n"
        "   - overview, description: text\n"
        "   - bullets: jsonb (use '[\"bullet 1\", \"bullet 2\"]'::jsonb)\n"
        "   - tags: jsonb (use '[\"Python\", \"PyTorch\"]'::jsonb)\n"
        "   - is_active: boolean (true if current/present)\n"
        "   - status_label: text (e.g. 'ACTIVE / 現職' or '歴任 / COMPLETED')\n"
        "   - kanji: text (single kanji, e.g. '木', '墨', '明', '原', '創')\n"
        "   - kanji_subtitle: text (2-5 uppercase chars e.g. 'AI', 'CRAFT', 'SYS')\n"
        "   - logo_url: text\n"
        "   - display_order: integer\n"
        "   - updated_at: timestamp with time zone (set to NOW())\n"
        "4. public.philosophy_pillars:\n"
        "   - position: integer (1, 2, or 3)\n"
        "   - kanji: text\n"
        "   - romaji: text\n"
        "   - title: text\n"
        "   - tag: text\n"
        "   - description: text\n"
        "   - updated_at: timestamp with time zone (set to NOW())\n"
        "5. public.resume_latex:\n"
        "   - id: integer\n"
        "   - content, resume_link, latex: text\n"
        "   - updated_at: timestamp with time zone (set to NOW())\n\n"
        "CRITICAL RULES:\n"
        "- Use PostgreSQL dollar-quoting ($$text$$) for string fields to avoid escaping bugs with quotes and newlines.\n"
        "- If user gives an exact text instruction for a specific field, map it 1-to-1 verbatim.\n"
        "- For unspecified fields, semantically infer appropriate, high-quality values matching context and portfolio style.\n"
        "- Never run DROP, TRUNCATE, ALTER, or unconditioned DELETE without a WHERE clause."
    ),
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

# Base tools available to all users (admin and guests)
BASE_TOOLS_SCHEMA = [get_vincent_info_tool, get_resume_tool]

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
