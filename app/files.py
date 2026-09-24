import base64
import io
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional
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
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def prepare_gemini_content(file_bytes: bytes, mime_type: str, client: genai.Client) -> Dict[str, Any]:
    """
    Universal Gemini file processor for ANY byte source (local assets or uploads).
    - Enforces universal maximum size limit.
    - Routes small files (<5MB) to inline base64 data for minimal latency.
    - Routes large files (>=5MB) to Gemini Files API using in-memory BytesIO (no temp files on disk).
    """
    file_size = len(file_bytes)

    # 1. Universal Maximum Size Check
    if file_size > settings.MAX_FILE_SIZE_BYTES:
        max_mb = settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File ({file_size / (1024 * 1024):.1f}MB) exceeds the maximum allowed limit of {max_mb}MB.",
        )

    category = "document" if any(k in mime_type for k in ("pdf", "word", "document", "msword")) else "image"

    # 2. Small files (<5MB): Inline base64 (fastest, in-memory)
    if file_size <= settings.INLINE_SIZE_LIMIT_BYTES:
        return {
            "type": category,
            "data": base64.b64encode(file_bytes).decode("utf-8"),
            "mime_type": mime_type,
        }

    # 3. Large files (>=5MB): Stream in-memory directly to Gemini Files API
    uploaded = client.files.upload(
        file=io.BytesIO(file_bytes),
        config={"mime_type": mime_type},
    )
    return {
        "type": category,
        "uri": uploaded.uri,
        "mime_type": uploaded.mime_type or mime_type,
    }


def validate_upload_magic_bytes(file_bytes: bytes, filename: Optional[str] = None) -> str:
    """
    Security guard for untrusted uploads: verifies magic bytes via filetype.
    Inspects 8KB to detect ZIP headers, OLE2 containers, and compound formats.
    """
    kind = filetype.guess(file_bytes[:8192])
    detected_mime = kind.mime if kind else None

    # Disambiguate DOCX inside ZIP container
    ext = Path(filename or "").suffix.lower()
    if detected_mime == "application/zip" and ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                if any(name.startswith("word/") for name in zf.namelist()):
                    detected_mime = DOCX_MIME
        except zipfile.BadZipFile:
            pass

    if not detected_mime or detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File format '{detected_mime or 'unknown'}' is unsupported or spoofed. "
                "Supported formats: PNG, JPEG, WEBP, GIF, PDF, DOCX, DOC."
            ),
        )

    return detected_mime


async def process_user_upload(file: UploadFile, client: genai.Client) -> Dict[str, Any]:
    """Upload endpoint pipeline: reads bytes, validates magic bytes, and formats for Gemini."""
    file_bytes = await file.read()
    mime_type = validate_upload_magic_bytes(file_bytes, file.filename)
    return prepare_gemini_content(file_bytes, mime_type, client)


# Backwards compatibility aliases if needed
validate_file_magic_bytes = validate_upload_magic_bytes
