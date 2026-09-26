import json
import hmac
from typing import Annotated, Optional, Union, Any
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import settings, client
from .security import get_user_context, UserContext, admin_token_context
from .agent import chat_with_agent, chat_with_agent_stream
from .files import process_user_upload
from .portfolio_service import invalidate_portfolio_cache, get_cache_status

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
        "thinking_level": settings.THINKING_LEVEL,
    }


@app.post("/api/v1/chat", response_model=Union[ChatResponse, Any])
async def chat_endpoint(
    # AUTH: Automatically extracted from 'Authorization: Bearer <token>' header
    user: Annotated[UserContext, Depends(get_user_context)],

    # PRODUCTION: Core user query (optional if a file attachment is provided)
    message: Annotated[Optional[str], Form(description="[Production UI] User question or prompt for the agent")] = None,
    
    # PRODUCTION: Multi-turn chat memory pointer
    previous_interaction_id: Annotated[Optional[str], Form(description="[Production UI] Thread ID from previous turn to maintain multi-turn chat context")] = None,
    
    # PRODUCTION (ADMIN-ONLY): Optional image or document attachment
    file: Annotated[Optional[UploadFile], File(description="[Admin Feature] Optional attachment (image, pdf, docx) to inspect")] = None,

    # PRODUCTION: Real-time streaming flag
    stream: Annotated[bool, Form(description="[Streaming] Stream response deltas in real-time via Server-Sent Events (SSE)")] = False,
):
    # Sanitize previous_interaction_id (ignore empty values or Swagger UI placeholder "string")
    clean_interaction_id = None
    if previous_interaction_id:
        val = previous_interaction_id.strip()
        if val and val.lower() not in ["string", "none", "null", "undefined", ""]:
            clean_interaction_id = val

    # Propagate active admin session token to downstream database tools
    if user.is_admin and user.raw_token:
        admin_token_context.set(user.raw_token)

    # 1. Security check and validation for file uploads and messages
    clean_message = message.strip() if message else ""
    if file is not None:
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="File uploads are restricted to administrators.",
            )

        # 2. Process uploaded file (magic-byte validation + Gemini preparation)
        file_payload = await process_user_upload(file, client)
        prompt_text = clean_message if clean_message else f"Please inspect and analyze the attached {file.filename or 'document'}."
        user_input = [file_payload, {"type": "text", "text": prompt_text}]
    else:
        # Standard plain text input
        if not clean_message:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Message cannot be empty.",
            )
        user_input = clean_message

    user_type = "Admin" if user.is_admin else ("Logged-in User" if user.is_authenticated else "Guest")

    # 3. Stream real-time tokens via Server-Sent Events (SSE) if requested
    if stream:
        def event_generator():
            try:
                yield f"data: {json.dumps({'type': 'init', 'user_type': user_type, 'model': settings.MODEL_NAME})}\n\n"
                for event in chat_with_agent_stream(
                    user_input=user_input,
                    is_admin=user.is_admin,
                    last_interaction_id=clean_interaction_id,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
            except HTTPException as http_exc:
                yield f"data: {json.dumps({'type': 'error', 'detail': http_exc.detail, 'status_code': http_exc.status_code})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'detail': str(exc), 'status_code': 500})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 4. Standard synchronous execution loop
    response_text, new_interaction_id, model_used = chat_with_agent(
        user_input=user_input,
        is_admin=user.is_admin,
        last_interaction_id=clean_interaction_id,
    )

    return ChatResponse(
        status="success",
        user_type=user_type,
        user_email=user.email or user.username,
        interaction_id=new_interaction_id,
        response=response_text,
        model=model_used,
    )


# =============================================================================
# SUPABASE DATABASE WEBHOOK CACHE INVALIDATION
# =============================================================================
class WebhookInvalidateResponse(BaseModel):
    status: str
    message: str
    table: Optional[str] = None
    event_type: Optional[str] = None
    invalidated_at: float
    was_cached: bool


class CacheStatusResponse(BaseModel):
    is_cached: bool
    cached_at: Optional[float] = None
    age_seconds: Optional[float] = None
    content_length_chars: int = 0


@app.post(
    "/api/v1/webhook/supabase-invalidate",
    response_model=WebhookInvalidateResponse,
    tags=["Webhooks"],
    summary="[Supabase Webhook] Invalidate server cache on database changes",
)
async def supabase_webhook_invalidate(
    request: Request,
    x_webhook_secret: Annotated[Optional[str], Header(alias="X-Webhook-Secret")] = None,
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
):
    """
    Receives database change events directly from Supabase Database Webhooks.
    Automatically invalidates the server-side in-memory portfolio context cache
    upon INSERT, UPDATE, or DELETE on portfolio tables.
    """
    expected_secret = settings.SUPABASE_WEBHOOK_SECRET.get_secret_value() if settings.SUPABASE_WEBHOOK_SECRET else None
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret is not configured on server.",
        )

    provided_secret = None
    if x_webhook_secret:
        provided_secret = x_webhook_secret.strip()
    elif authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_secret = parts[1]
        else:
            provided_secret = authorization.strip()

    if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid webhook secret.",
        )

    table_name = None
    event_type = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            table_name = body.get("table")
            event_type = body.get("type")
    except Exception:
        pass

    inv_result = invalidate_portfolio_cache()

    return WebhookInvalidateResponse(
        status="success",
        message="Portfolio cache invalidated via Supabase database webhook.",
        table=table_name,
        event_type=event_type,
        invalidated_at=inv_result["invalidated_at"],
        was_cached=inv_result["was_cached"],
    )


@app.get(
    "/api/v1/admin/cache/status",
    response_model=CacheStatusResponse,
    tags=["Cache Management"],
    summary="[Admin] Inspect server-side cache status",
)
def cache_status(
    user: Annotated[UserContext, Depends(get_user_context)],
):
    """Inspects the current server cache state (cached_at timestamp, age, size)."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to inspect cache status.",
        )
    return CacheStatusResponse(**get_cache_status())