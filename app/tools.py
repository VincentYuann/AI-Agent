import base64
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

# Resolve ASSETS_DIR using pathlib
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
if not ASSETS_DIR.exists():
    ASSETS_DIR = Path(__file__).resolve().parent / "assets"


# -------------------------------------------------------------
# 1. LOCAL ASSET LOADERS (Cached in memory)
# -------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_champ_tier_list_base64() -> str:
    """Cache the base64 string of the tier list image in memory."""
    image_path = ASSETS_DIR / "champ_tier_list.webp"
    if not image_path.exists():
        return ""
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


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
def get_champ_tier_list() -> list[dict]:
    """Returns the multimodal content block for the champion tier list image."""
    tier_data = _load_champ_tier_list_base64()
    if not tier_data:
        return [{"type": "text", "text": "Champion tier list image is unavailable."}]
    return [
        {"type": "text", "text": "champ_tier_list.webp"},
        {
            "type": "image",
            "mime_type": "image/webp",
            "data": tier_data,
        },
    ]


def get_resume() -> list[dict]:
    """Returns the text content of Vincent Yuan's resume."""
    return [{"type": "text", "text": _load_resume_text()}]


# -------------------------------------------------------------
# 3. TOOL SCHEMAS & REGISTRY
# -------------------------------------------------------------
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
    "description": "Returns Vincent Yuan's resume text. Call this tool when answering questions about Vincent's experience, skills, education, or portfolio.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

BASE_TOOLS_SCHEMA = [get_champ_tier_list_tool, get_resume_tool]

TOOL_FUNCTIONS = {
    "get_champ_tier_list": get_champ_tier_list,
    "get_resume": get_resume,
}


def get_agent_tools(is_admin: bool) -> List[Dict[str, Any]]:
    """Returns the tools for the portfolio assistant."""
    return list(BASE_TOOLS_SCHEMA)
