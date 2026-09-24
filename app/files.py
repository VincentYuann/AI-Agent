import base64
import tempfile
from pathlib import Path
from fastapi import HTTPException, status, UploadFile
import filetype
from google import genai

from .config import settings

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


async def validate_file_magic_bytes(file: UploadFile) -> str:
    """Reads header magic bytes to verify actual MIME type against spoofing."""
    header = await file.read(2048)
    await file.seek(0)

    kind = filetype.guess(header)
    detected_mime = kind.mime if kind else file.content_type

    # Fallback for Word document packages
    ext = Path(file.filename or "").suffix.lower()
    if ext == ".docx":
        detected_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == ".doc":
        detected_mime = "application/msword"

    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{detected_mime}' is not permitted. Supported formats: PNG, JPEG, WEBP, GIF, PDF, DOCX.",
        )
    return detected_mime


async def process_file_for_gemini(file: UploadFile, detected_mime: str, client: genai.Client) -> dict:
    """
    Reads small files (<5MB) inline into memory or streams large files (>=5MB)
    to the Gemini Files API via pathlib.Path.
    """
    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size / (1024 * 1024):.1f}MB) exceeds the maximum allowed limit of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    content_category = "document" if "pdf" in detected_mime or "word" in detected_mime else "image"

    # CASE 1: Small file -> Inline data (kept in-memory for speed)
    if file_size <= settings.INLINE_SIZE_LIMIT_BYTES:
        return {
            "type": content_category,
            "data": base64.b64encode(file_bytes).decode("utf-8"),
            "mime_type": detected_mime,
        }

    # CASE 2: Large file -> Gemini Files API via temporary Path
    temp_dir = Path(tempfile.gettempdir()) / "agent_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / Path(file.filename or "upload.tmp").name

    try:
        temp_file_path.write_bytes(file_bytes)
        uploaded = client.files.upload(file=str(temp_file_path))
        return {
            "type": content_category,
            "uri": uploaded.uri,
            "mime_type": uploaded.mime_type or detected_mime,
        }
    finally:
        if temp_file_path.exists():
            temp_file_path.unlink()
