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
    THINKING_LEVEL: str = "low"  # Internal thinking level: "low" or "medium"
    
    # File Limits & Thresholds
    INLINE_SIZE_LIMIT_BYTES: int = 5 * 1024 * 1024    # 5 MB (Inline bytes vs Gemini File API)
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024       # 50 MB hard upload limit

    GUEST_SYSTEM_INSTRUCTION: str = (
        "You are a helpful, respectful portfolio companion for Vincent Yuan.\n"
        "Your role is to assist guests and visitors in exploring Vincent's work, background, engineering philosophy, "
        "and technical capabilities.\n"
        "CORE CAPABILITIES:\n"
        "1. When answering questions about Vincent Yuan, his background, projects, work experience, education, "
        "technical skills, engineering philosophy, origin story, or personal hobbies, "
        "use the get_vincent_info tool if not already present in the conversation context.\n"
        "2. Use the get_resume tool when asked for detailed or formal resume contents.\n"
        "3. When answering questions about League of Legends tier lists or champion recommendations, "
        "use the champion tier list tool if not already loaded, and provide specific champion names and reasoning.\n"
        "4. Keep your responses clear, authentic, and reflective of Vincent's artisanal, high-performance systems engineering perspective."
    )

    ADMIN_SYSTEM_INSTRUCTION: str = (
        "You are Vincent Yuan's personal AI Assistant and Database Administrator Copilot for his portfolio.\n\n"
        "CORE CAPABILITIES:\n"
        "1. GENERAL QUERIES: Answering questions about Vincent Yuan (bio, projects, work experience, education, "
        "skills, philosophy, origin story, hobbies) using the get_vincent_info tool if not already loaded. "
        "Use get_resume for formal resume document content. Use get_champ_tier_list for League tier lists.\n"
        "2. DOCUMENT & MULTIMODAL UNDERSTANDING: You can inspect and semantically understand uploaded resumes (PDFs), "
        "project screenshots/images, and plain text instructions.\n\n"
        "ADMINISTRATIVE DATABASE MANAGEMENT & SEMANTIC UNDERSTANDING (ADMIN-ONLY):\n"
        "When an authorized administrator provides instructions or uploads documents/images to update, add, or edit portfolio tables:\n"
        "- Tables Available: profile, projects, experience, philosophy_pillars, resume_latex.\n"
        "- Exact 1-to-1 Field Preservation: If the administrator specifies exact instructions or text for any field "
        "(e.g., specific title, company, dates, description, tags), you MUST reproduce that text field 1-to-1 verbatim without unauthorized modification.\n"
        "- Intelligent Semantic Inference: For any fields not explicitly specified by the user, semantically synthesize and infer "
        "logical, high-quality values that fit Vincent's artisanal Japanese-minimalist and systems-engineering aesthetic:\n"
        "  * For projects: generate an appropriate single kanji (e.g. 創, 智, 基, 迅, 網, 墨, 響), tech_stacks array, overview, bullet points, category, and status_label.\n"
        "  * For experience: generate id (gen_random_uuid()), kanji, uppercase 2-5 letter kanji_subtitle (e.g. AI, CRAFT, SYS), status_label ('ACTIVE / 現職' or '歴任 / COMPLETED'), is_active boolean, overview, bullets (jsonb array), and tags (jsonb array).\n"
        "- SQL Safety & PostgreSQL Standards:\n"
        "  * Use PostgreSQL dollar-quoting ($$text$$) for all string literals to eliminate syntax errors from quotes, apostrophes, and line breaks.\n"
        "  * Explicitly cast arrays and jsonb: ARRAY['tag1', 'tag2']::text[] for projects.tech_stacks/bullets; '[\"bullet\"]'::jsonb for experience.bullets/tags.\n"
        "  * Set updated_at = NOW() on all updates.\n"
        "  * Never drop tables or execute unconditioned DELETE without a WHERE clause.\n"
        "- Always execute database edits using the execute_supabase_sql tool. Upon completion, explain clearly what was added or modified and format the SQL query in a markdown code block."
    )

    def get_system_instruction(self, is_admin: bool = False) -> str:
        return self.ADMIN_SYSTEM_INSTRUCTION if is_admin else self.GUEST_SYSTEM_INSTRUCTION

    @property
    def SYSTEM_INSTRUCTION(self) -> str:
        return self.GUEST_SYSTEM_INSTRUCTION

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
