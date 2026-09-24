# Vincent Yuan AI Agent Backend

A production-grade, secure **FastAPI** backend powering an AI portfolio assistant and multimodal document analyzer using the **Google Gemini Interactions API**, **Supabase JWT Authentication**, and **Role-Based Access Control (RBAC)**.

---

## 🌟 Key Architecture & Features

### 1. Transitioned from Legacy CLI to Modern FastAPI Service
* **Decoupled Architecture**: Transitioned from a terminal `input()` loop to a modular REST API with full OpenAPI / Swagger UI documentation (`/docs`).
* **Clean Separation of Concerns**:
  * `app/config.py`: Centralized type-safe configuration via `pydantic-settings`.
  * `app/security.py`: Stateless Supabase JWT verification and dynamic admin role checking.
  * `app/files.py`: Path traversal protection, magic-byte inspection, and hybrid file routing (Inline vs. Gemini File API).
  * `app/tools.py`: In-memory cached portfolio tools (`get_resume`, `get_champ_tier_list`).
  * `app/agent.py`: Google GenAI Interactions API execution engine with multi-turn conversation and function-calling loop.
  * `app/main.py`: FastAPI application factory, health check, and endpoints.

### 2. Role-Based Security & Supabase Auth
* **Public / Guest Access**: Anyone can chat with the assistant via text to ask about Vincent's experience, skills, education, and portfolio.
* **Admin-Only Features**: File uploads (images, screenshots, PDFs, Word docs) and elevated tool access are strictly restricted to authenticated Supabase Administrators (identified via JWT claims or configured admin emails).
* **Swagger UI Integration**: Uses `HTTPBearer(auto_error=False)` allowing guests to test the API directly without 401 errors, while admins can authenticate using the green **Authorize** button in Swagger UI.

### 3. Secure Multimodal File Processing
* **Magic-Byte Inspection**: Uses `filetype` to inspect the first 2048 bytes of uploaded files on the server to prevent extension and MIME-type spoofing.
* **Path Traversal Protection**: Uses `pathlib.Path(file.filename).name` to strip malicious relative path sequences (`../`).
* **Hybrid Upload Strategy**:
  * **Files < 5MB**: Processed in-memory as Base64 payloads (fast, zero server disk I/O).
  * **Files >= 5MB up to 50MB**: Streamed to temporary storage, uploaded to the Gemini Files API, and safely unlinked in a `finally` block.

### 4. High-Throughput Model & Rate-Limit Resilience
* Powered by **`gemini-3.6-flash`**, providing **1,500 free requests per day (RPD)** and **15 requests per minute (RPM)**.
* Graceful HTTP `429 Too Many Requests` handling prevents server crashes or unhandled tracebacks.

---

## 📂 Project Structure

```text
AI Agent/
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules (protects secrets & virtualenvs)
├── Dockerfile                # Multi-stage container build with Python 3.13 & uv
├── pyproject.toml            # Project dependencies & metadata
├── uv.lock                   # Deterministic dependency lockfile
├── assets/                   # Portfolio assets (Resume PDF, tier list image)
│   ├── Vincent_Yuan_Resume.pdf
│   └── champ_tier_list.webp
└── app/
    ├── __init__.py
    ├── config.py             # Settings & Gemini Client initialization
    ├── security.py           # Supabase JWT decoding & dynamic Admin verification
    ├── files.py              # Magic-byte detection & Gemini file processing
    ├── tools.py              # Cached local tools & tool schema definitions
    ├── agent.py              # Gemini Interactions API loop & tool runner
    └── main.py               # FastAPI app & POST /api/v1/chat endpoint
```

---

## 🚀 Getting Started

### Prerequisites
* Python `>= 3.13`
* [`uv`](https://github.com/astral-sh/uv) (recommended fast package manager)

### 1. Clone & Install Dependencies
```bash
git clone <your-repo-url>
cd "AI Agent"
uv sync
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Edit `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SUPABASE_JWT_SECRET=your_supabase_jwt_secret_here
ADMIN_EMAILS=vincentyuan1020@gmail.com
ADMIN_ROLES=admin,service_role
ENVIRONMENT=development
```

### 3. Run the Development Server
```bash
uv run uvicorn app.main:app --reload
```

Server will be running at: `http://127.0.0.1:8000`
Interactive API Docs (Swagger UI): `http://127.0.0.1:8000/docs`

---

## 🧪 API Endpoints

### 1. Health Check
`GET /`
```json
{
  "status": "healthy",
  "service": "Vincent Yuan AI Agent Backend",
  "environment": "development",
  "model": "gemini-3.6-flash"
}
```

### 2. Chat with Agent
`POST /api/v1/chat` (Content-Type: `multipart/form-data`)

**Form Fields:**
* `message` *(required, string)*: The prompt or question.
* `previous_interaction_id` *(optional, string)*: Interaction ID for stateful multi-turn conversations.
* `file` *(optional, file upload, Admin only)*: Attached image, screenshot, PDF, or DOCX.

**Responses:**
* `200 OK`: Successful response containing `user_type`, `interaction_id`, and `response`.
* `403 Forbidden`: Returned when a guest or non-admin attempts to upload a file.
* `415 Unsupported Media Type`: Returned if an uploaded file fails magic-byte validation.
* `429 Too Many Requests`: Returned when Google API quota limits are reached.

---

## 🐳 Docker Deployment

Build and run using Docker:

```bash
docker build -t vincent-ai-agent .
docker run -p 8000:8000 --env-file .env vincent-ai-agent
```

---

## 🔒 Security Summary
* Secrets are loaded via `pydantic-settings` using `SecretStr` to prevent accidental logging.
* JWT validation strictly enforces the HMAC-SHA256 signature algorithm against `SUPABASE_JWT_SECRET`.
* No sensitive API keys or credentials are committed to version control.
