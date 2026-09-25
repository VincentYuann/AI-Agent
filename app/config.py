from typing import List, Union, Optional
from google import genai
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Dynamic Admin Verification (Configured exclusively via .env, never hardcoded in code)
    ADMIN_EMAILS: Union[List[str], str] = ""
    ADMIN_USERNAMES: Union[List[str], str] = ""
    ADMIN_ROLES: Union[List[str], str] = "admin,service_role"

    # CORS Allowed Origins
    ALLOWED_ORIGINS: List[str] = [
        "https://vincentyuann.github.io",
        "http://localhost:5173",
    ]

    # Official Production Flash Model: gemini-3.6-flash (1,500 requests/day, 15 req/min on free tier)
    MODEL_NAME: str = "gemini-3.6-flash"
    
    # File Limits & Thresholds
    INLINE_SIZE_LIMIT_BYTES: int = 5 * 1024 * 1024    # 5 MB (Inline bytes vs Gemini File API)
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024       # 50 MB hard upload limit

    SYSTEM_INSTRUCTION: str = (
        "You are a helpful portfolio assistant for Vincent Yuan. "
        "When answering questions about Vincent Yuan, his education, skills, projects, or work experience, "
        "use the resume tool if not already in context. "
        "When answering questions about League of Legends tier lists or champion recommendations, "
        "use the champion tier list tool if not already loaded, "
        "and give specific champion names and reasoning based on the tier list. "
        "You can also inspect and answer questions about any documents or images uploaded by the user."
    )

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


settings = Settings()

# Automatically initializes Gemini client with API key from settings
client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())
