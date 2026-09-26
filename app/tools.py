import json
import logging
import re
from html import unescape
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
import httpx
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


def web_search(query: str) -> list[dict]:
    """
    Performs a live web search to find current information, external facts, or documentation.
    Extracts relevant snippets, titles, and links.
    """
    logger.info(f"Executing web search for query: {query}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://html.duckduckgo.com/",
        }
        with httpx.Client(timeout=10.0, follow_redirects=True) as http_client:
            resp = http_client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=headers,
            )

        if resp.status_code != 200:
            return [{"type": "text", "text": f"Search returned status code {resp.status_code}."}]

        raw_results = re.findall(
            r'<h2 class="result__title">.*?<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        )

        results = []
        for link, title_html, snippet_html in raw_results[:5]:
            title = unescape(re.sub(r'<[^>]+>', '', title_html)).strip()
            snippet = unescape(re.sub(r'<[^>]+>', '', snippet_html)).strip()
            results.append(f"Title: {title}\nURL: {link.strip()}\nSummary: {snippet}")

        if not results:
            snippets = re.findall(r'class="result__snippet[^"]*"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
            for snip in snippets[:5]:
                clean = unescape(re.sub(r'<[^>]+>', '', snip)).strip()
                results.append(clean)

        output_text = "\n\n".join(results) if results else "No relevant search results found."
        return [{"type": "text", "text": output_text}]
    except Exception as e:
        logger.error(f"Error performing web search: {e}")
        return [{"type": "text", "text": f"Web search error: {str(e)}"}]



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

web_search_tool = {
    "type": "function",
    "name": "web_search",
    "description": (
        "Performs a live web search to find current information, recent news, external articles, "
        "or facts not present in Vincent's database. Call this tool whenever you feel you need "
        "more information, external documentation, or up-to-date facts to answer the user's question accurately."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string to look up on the web.",
            }
        },
        "required": ["query"],
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
url_context_tool = {"type": "url_context"}

# Base tools available to all users (admin and guests)
BASE_TOOLS_SCHEMA = [url_context_tool, get_vincent_info_tool, get_resume_tool, web_search_tool]

TOOL_FUNCTIONS = {
    "get_vincent_info": get_vincent_info,
    "get_resume": get_resume,
    "execute_supabase_sql": execute_supabase_sql_action,
    "web_search": web_search,
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
