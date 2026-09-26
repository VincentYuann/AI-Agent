from pathlib import Path
from functools import lru_cache
from typing import List, Union, Optional
from google import genai
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=8)
def load_prompt_file(filename: str) -> str:
    """Loads and caches prompt markdown files from the prompts directory."""
    path = PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    fallback = Path(__file__).resolve().parent.parent / "assets" / filename
    if fallback.exists():
        return fallback.read_text(encoding="utf-8").strip()
    return ""


def load_writing_style_guide() -> str:
    """Backward compatibility helper for style guide."""
    return load_prompt_file("writing_style_guide.md")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore"
    )

    PROJECT_NAME: str = "Vincent Yuan AI Agent Backend"
    ENVIRONMENT: str = "development"

    # API Keys & Auth Secrets
    GEMINI_API_KEY: SecretStr
    SUPABASE_JWT_SECRET: SecretStr
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[SecretStr] = None
    SUPABASE_WEBHOOK_SECRET: Optional[SecretStr] = None

    # Dynamic Admin Verification (Configured exclusively via .env, never hardcoded in code)
    ADMIN_EMAILS: Union[List[str], str] = ""
    ADMIN_USERNAMES: Union[List[str], str] = ""
    ADMIN_ROLES: Union[List[str], str] = "admin,service_role"

    # CORS Allowed Origins
    ALLOWED_ORIGINS: List[str] = [
        "https://vincentyuann.github.io",
        "http://localhost:5173",
    ]

    # Production Model (500 RPD on Free Tier)
    MODEL_NAME: str = "gemini-3.5-flash-lite"
    THINKING_LEVEL: str = "medium"  # Internal thinking level: "low" or "medium"
    
    # File Limits & Thresholds
    INLINE_SIZE_LIMIT_BYTES: int = 5 * 1024 * 1024    # 5 MB (Inline bytes vs Gemini File API)
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024       # 50 MB hard upload limit

    @property
    def GUEST_SYSTEM_INSTRUCTION(self) -> str:
        return load_prompt_file("guest_instruction.md")

    @property
    def ADMIN_SYSTEM_INSTRUCTION(self) -> str:
        return load_prompt_file("admin_instruction.md")

    def get_system_instruction(self, is_admin: bool = False) -> str:
        base = self.ADMIN_SYSTEM_INSTRUCTION if is_admin else self.GUEST_SYSTEM_INSTRUCTION
        style_guide = load_prompt_file("writing_style_guide.md")
        if style_guide:
            return f"{base}\n\n{style_guide}"
        return base

    @property
    def SYSTEM_INSTRUCTION(self) -> str:
        return self.get_system_instruction(is_admin=False)

    @property
    def admin_emails_list(self) -> List[str]:
        if isinstance(self.ADMIN_EMAILS, list):
            return [e.strip().lower() for e in self.ADMIN_EMAILS if e.strip()]
        return [e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()]

    @property
    def admin_usernames_list(self) -> List[str]:
        if isinstance(self.ADMIN_USERNAMES, list):
            return [u.strip().lower() for u in self.ADMIN_USERNAMES if u.strip()]
        return [u.strip().lower() for u in self.ADMIN_USERNAMES.split(",") if u.strip()]

    @property
    def admin_roles_list(self) -> List[str]:
        if isinstance(self.ADMIN_ROLES, list):
            return [r.strip() for r in self.ADMIN_ROLES if r.strip()]
        return [r.strip() for r in self.ADMIN_ROLES.split(",") if r.strip()]


# Automatically initializes Gemini client with API key from settings
settings = Settings()
client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
