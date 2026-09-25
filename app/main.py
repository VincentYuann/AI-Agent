from typing import Annotated, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field

from .config import settings, client
from .security import get_user_context, UserContext
from .agent import chat_with_agent
from .files import process_user_upload

from fastapi.middleware.cors import CORSMiddleware

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

# Enable CORS strictly for Vincent's portfolio frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


class ChatResponse(BaseModel):
    # =========================================================================
    # PRODUCTION FRONTEND FIELDS (Strictly required for chat UI operation)
    # =========================================================================
    response: str = Field(
        ...,
        description="[Production UI] The agent's generated reply text to display in the chat window."
    )
    interaction_id: Optional[str] = Field(
        None,
        description="[Production UI] Thread ID to store in frontend state and send back for continuing multi-turn chats."
    )

    # =========================================================================
    # SWAGGER / DEBUG FIELDS (For verification and testing in /docs without checking server logs)
    # =========================================================================
    user_type: str = Field(
        ...,
        description="[Swagger / Debug] Identifies caller privileges: 'Admin', 'Logged-in User', or 'Guest'."
    )
    user_email: Optional[str] = Field(
        None,
        description="[Swagger / Debug] Verified email address or GitHub username from decoded Supabase JWT."
    )
    status: str = Field(
        "success",
        description="[REST Standard] HTTP response wrapper status string."
    )
    model: Optional[str] = Field(
        None,
        description="[REST Standard] Identifies which Gemini model generated the response."
    )


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
    # PRODUCTION: Core user query
    message: Annotated[str, Form(description="[Production UI] User question or prompt for the agent")],
    
    # AUTH: Automatically extracted from 'Authorization: Bearer <token>' header
    user: Annotated[UserContext, Depends(get_user_context)],
    
    # PRODUCTION: Multi-turn chat memory pointer
    previous_interaction_id: Annotated[Optional[str], Form(description="[Production UI] Thread ID from previous turn to maintain multi-turn chat context")] = None,
    
    # PRODUCTION (ADMIN-ONLY): Optional image or document attachment
    file: Annotated[Optional[UploadFile], File(description="[Admin Feature] Optional attachment (image, pdf, docx) to inspect")] = None,
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
                detail="File uploads are restricted to administrators.",
            )

        # 2. Process uploaded file (magic-byte validation + Gemini preparation)
        file_payload = await process_user_upload(file, client)
        user_input = [file_payload, {"type": "text", "text": message}]
    else:
        # Standard plain text input
        user_input = message

    # 4. Execute agent interactions loop
    response_text, new_interaction_id, model_used = chat_with_agent(
        user_input=user_input,
        is_admin=user.is_admin,
        last_interaction_id=clean_interaction_id,
    )

    user_type = "Admin" if user.is_admin else ("Logged-in User" if user.is_authenticated else "Guest")

    return ChatResponse(
        status="success",
        user_type=user_type,
        user_email=user.email or user.username,
        interaction_id=new_interaction_id,
        response=response_text,
        model=model_used,
    )