from typing import Annotated, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel

from .config import settings, client
from .security import get_user_context, UserContext
from .agent import chat_with_agent
from .files import validate_file_magic_bytes, process_file_for_gemini

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Production AI Agent API.\n\n"
        "**Access Control:**\n"
        "- **Guests / Normal Users:** Allowed conversational text chat with the agent.\n"
        "- **Admins (Supabase Auth):** Granted permission to upload attachments (images/PDFs/DOCX) and use agent tools.\n\n"
        "To test as an Admin in this Swagger UI, click the **Authorize** button at the top right and paste your Supabase JWT."
    ),
    version="1.0.0",
)


class ChatResponse(BaseModel):
    status: str
    user_type: str
    user_email: Optional[str] = None
    interaction_id: Optional[str] = None
    response: str


@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "model": settings.MODEL_NAME,
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(
    message: Annotated[str, Form(description="User prompt or question for the agent")],
    user: Annotated[UserContext, Depends(get_user_context)],
    previous_interaction_id: Annotated[Optional[str], Form(description="Optional: Interaction ID for continuing multi-turn chats")] = None,
    file: Annotated[Optional[UploadFile], File(description="Admin-only: image, screenshot, pdf, or docx attachment")] = None,
):
    # Sanitize previous_interaction_id (ignore empty values or Swagger UI placeholder "string")
    clean_interaction_id = None
    if previous_interaction_id:
        val = previous_interaction_id.strip()
        if val and val.lower() not in ["string", "none", "null", "undefined", ""]:
            clean_interaction_id = val

    # 1. Security check for file uploads
    if file is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="File uploads to the agent are restricted to Supabase administrators only.",
            )

        # 2. Magic-byte verification
        detected_mime = await validate_file_magic_bytes(file)

        # 3. Prepare Gemini content (inline base64 if < 5MB or Gemini File API if >= 5MB)
        file_payload = await process_file_for_gemini(file, detected_mime, client)
        user_input = [file_payload, {"type": "text", "text": message}]
    else:
        # Standard plain text input
        user_input = message

    # 4. Execute agent interactions loop
    response_text, new_interaction_id = chat_with_agent(
        user_input=user_input,
        is_admin=user.is_admin,
        last_interaction_id=clean_interaction_id,
    )

    user_type = "Admin" if user.is_admin else ("Logged-in User" if user.is_authenticated else "Guest")

    return ChatResponse(
        status="success",
        user_type=user_type,
        user_email=user.email,
        interaction_id=new_interaction_id,
        response=response_text,
    )