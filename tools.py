import base64
from functools import lru_cache
import os
from pypdf import PdfReader

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

# -------------------------------------------------------------
# 1. LOCAL ASSET LOADERS
# -------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_champ_tier_list_base64() -> str:
    """Cache the base64 string in memory to avoid repeated disk reads."""
    image_path = os.path.join(ASSETS_DIR, "champ_tier_list.webp")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


@lru_cache(maxsize=1)
def _load_resume_text() -> str:
    """Extract and cache resume text using PdfReader."""
    resume_path = os.path.join(ASSETS_DIR, "Vincent_Yuan_Resume.pdf")
    reader = PdfReader(resume_path)
    return "\n".join([page.extract_text() or "" for page in reader.pages])


# -------------------------------------------------------------
# 2. TOOL EXECUTION FUNCTIONS (Enforced list[dict] output)
# -------------------------------------------------------------
def get_champ_tier_list() -> list[dict]:
    """Returns the multimodal content block for the champion tier list image."""
    return [
        {"type": "text", "text": "champ_tier_list.webp"},
        {
            "type": "image",
            "mime_type": "image/webp",
            "data": _load_champ_tier_list_base64(),
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

TOOLS_SCHEMA = [get_champ_tier_list_tool, get_resume_tool]

TOOL_FUNCTIONS = {
    "get_champ_tier_list": get_champ_tier_list,
    "get_resume": get_resume,
}

