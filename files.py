import filetype
import os
import mimetypes
from config import client


def upload_file_for_interaction(file_path: str) -> dict:
    """Uploads a local file using the Gemini Files API and returns the multimodal content block."""
    clean_path = file_path.strip().strip('"').strip("'")
    if not os.path.exists(clean_path):
        raise FileNotFoundError(f"File not found: {clean_path}")

    uploaded_file = client.files.upload(file=clean_path)
    mime = (uploaded_file.mime_type or "").lower()
    part_type = "image" if mime.startswith("image/") else "document"

    return {
        "type": part_type,
        "uri": uploaded_file.uri,
        "mime_type": uploaded_file.mime_type,
    }
