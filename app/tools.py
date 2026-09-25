from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

from .config import client
from .files import prepare_gemini_content
from .portfolio_service import get_portfolio_context, invalidate_portfolio_cache

# Resolve ASSETS_DIR using pathlib
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
if not ASSETS_DIR.exists():
    ASSETS_DIR = Path(__file__).resolve().parent / "assets"


# -------------------------------------------------------------
# 1. LOCAL ASSET LOADERS (Cached in memory)
# -------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_champ_tier_list_payload() -> Dict[str, Any]:
    """Cache the prepared Gemini payload for the champion tier list image."""
    image_path = ASSETS_DIR / "champ_tier_list.webp"
    if not image_path.exists():
        return {"type": "text", "text": "Champion tier list image is unavailable."}
    return prepare_gemini_content(
        file_bytes=image_path.read_bytes(),
        mime_type="image/webp",
        client=client,
    )


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


def get_champ_tier_list() -> list[dict]:
    """Returns the multimodal content block for the champion tier list image."""
    payload = _load_champ_tier_list_payload()
    return [
        {"type": "text", "text": "champ_tier_list.webp"},
        payload,
    ]


def get_resume() -> list[dict]:
    """Returns the text content of Vincent Yuan's resume."""
    return [{"type": "text", "text": _load_resume_text()}]


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

get_champ_tier_list_tool = {
    "type": "function",
    "name": "get_champ_tier_list",
    "description": "Returns the League of Legends champion tier list image. Call this tool when answering questions regarding champion tiers, meta rankings, tier lists, or strong picks if not already in context.",
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

# Base tools available to all users (admin and guests)
BASE_TOOLS_SCHEMA = [get_vincent_info_tool, get_resume_tool, get_champ_tier_list_tool]

TOOL_FUNCTIONS = {
    "get_vincent_info": get_vincent_info,
    "get_champ_tier_list": get_champ_tier_list,
    "get_resume": get_resume,
}


def get_agent_tools(is_admin: bool = False) -> List[Dict[str, Any]]:
    """Returns the tools for the portfolio assistant."""
    return list(BASE_TOOLS_SCHEMA)
