import io
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.config import load_prompt_file, settings
from app.files import (
    validate_upload_magic_bytes,
    prepare_gemini_content,
    ALLOWED_MIME_TYPES,
)
from tests.test_portfolio_cache import create_mock_jwt

client = TestClient(app)


def test_load_system_prompt_md_files():
    """Verifies that system prompt markdown files are loaded and cached in memory."""
    # Ensure cache exists
    assert hasattr(load_prompt_file, "cache_info")

    content = load_prompt_file("writing_style_guide.md")
    assert len(content) > 0
    assert "Vincent" in content or "Architecture" in content or "Style" in content

    # Check cache hit
    info_before = load_prompt_file.cache_info()
    _ = load_prompt_file("writing_style_guide.md")
    info_after = load_prompt_file.cache_info()
    assert info_after.hits > info_before.hits

    # Check non-existent file returns empty string gracefully
    missing = load_prompt_file("non_existent_file_xyz.md")
    assert missing == ""


def test_validate_upload_magic_bytes():
    """Verifies magic byte detection and extension disambiguation for text and binary files."""
    # 1. Plain Markdown file
    md_bytes = b"# Architecture Design Document\nThis is a sample markdown file."
    assert validate_upload_magic_bytes(md_bytes, "design.md") == "text/markdown"
    assert validate_upload_magic_bytes(md_bytes, "notes.markdown") == "text/markdown"

    # 2. Plain Text file
    txt_bytes = b"Just plain text notes."
    assert validate_upload_magic_bytes(txt_bytes, "notes.txt") == "text/plain"

    # 3. PDF binary magic bytes (%PDF)
    pdf_bytes = b"%PDF-1.5 \x00\x01\x02 test pdf dummy content"
    assert validate_upload_magic_bytes(pdf_bytes, "resume.pdf") == "application/pdf"

    # 4. PNG binary magic bytes
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 20
    assert validate_upload_magic_bytes(png_bytes, "diagram.png") == "image/png"

    # 5. Unsupported binary file (e.g. random executable bytes)
    exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
    with pytest.raises(HTTPException) as exc_info:
        validate_upload_magic_bytes(exe_bytes, "program.exe")
    assert exc_info.value.status_code == 415


def test_prepare_gemini_content_markdown_formatting():
    """Verifies that uploaded markdown files are formatted with document boundaries and filename metadata."""
    md_bytes = b"# My Project\nDetails about system design."
    dummy_genai_client = None

    payload = prepare_gemini_content(
        file_bytes=md_bytes,
        mime_type="text/markdown",
        client=dummy_genai_client,
        filename="project_spec.md",
    )

    assert payload["type"] == "text"
    assert "--- Attached Document: project_spec.md (text/markdown) ---" in payload["text"]
    assert "# My Project" in payload["text"]
    assert "--- End of Attached Document ---" in payload["text"]


def test_prepare_gemini_content_size_limits():
    """Verifies that files exceeding MAX_FILE_SIZE_BYTES are rejected with 413."""
    oversized_bytes = b"0" * (settings.MAX_FILE_SIZE_BYTES + 1024)
    dummy_genai_client = None

    with pytest.raises(HTTPException) as exc_info:
        prepare_gemini_content(
            file_bytes=oversized_bytes,
            mime_type="application/pdf",
            client=dummy_genai_client,
            filename="massive.pdf",
        )
    assert exc_info.value.status_code == 413


def test_chat_endpoint_file_guest_rejection():
    """Verifies that non-admin (guest or unauthorized user) file uploads are rejected with 403."""
    md_content = io.BytesIO(b"# Secret notes")
    response = client.post(
        "/api/v1/chat",
        data={"message": "Please review this"},
        files={"file": ("notes.md", md_content, "text/markdown")},
    )
    assert response.status_code == 403
    assert "restricted to administrators" in response.json()["detail"]


def test_chat_endpoint_empty_message_validation():
    """Verifies that empty string messages without files are rejected with 422."""
    response = client.post(
        "/api/v1/chat",
        data={"message": "   "},
    )
    assert response.status_code == 422
    assert "Message cannot be empty" in response.json()["detail"]


def test_chat_endpoint_admin_file_upload_mocked(monkeypatch):
    """Verifies admin uploading a markdown file with default prompt generation."""
    captured_inputs = []

    def mock_chat_stream(user_input, is_admin, last_interaction_id):
        captured_inputs.append((user_input, is_admin, last_interaction_id))
        yield {"type": "delta", "text": "File analyzed successfully."}
        yield {"type": "done", "interaction_id": "mock-interaction-id-999"}

    monkeypatch.setattr("app.agent.chat_with_agent_stream", mock_chat_stream)
    monkeypatch.setattr("app.main.chat_with_agent_stream", mock_chat_stream)

    admin_token = create_mock_jwt("vincentyuan1020@gmail.com")
    md_file = io.BytesIO(b"# Architecture Spec\nHigh performance caching.")

    response = client.post(
        "/api/v1/chat",
        headers={"Authorization": f"Bearer {admin_token}"},
        data={"message": "", "stream": "false"},  # Empty message -> should default
        files={"file": ("architecture.md", md_file, "text/markdown")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["user_type"] == "Admin"

    # Verify captured input has the document framing and default prompt
    assert len(captured_inputs) == 1
    input_payload, is_admin_val, _ = captured_inputs[0]
    assert is_admin_val is True
    assert isinstance(input_payload, list)
    assert len(input_payload) == 2
    # Document payload
    assert input_payload[0]["type"] == "text"
    assert "--- Attached Document: architecture.md (text/markdown) ---" in input_payload[0]["text"]
    # Prompt payload
    assert input_payload[1]["type"] == "text"
    assert "Please inspect and analyze the attached architecture.md." in input_payload[1]["text"]
