from fastapi import FastAPI, UploadFile, File
from pypdf import PdfReader
import base64
from functools import lru_cache
import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

load_dotenv()
client = genai.Client()  # automatically reads GEMINI_API_KEY from environment
MODEL_NAME = "gemini-3.5-flash-lite"
SYSTEM_INSTRUCTION = (
    "You are a helpful portfolio assistant for Vincent Yuan. "
    "When answering questions about Vincent Yuan, his education, skills, projects, or work experience, "
    "use the resume tool if not already in context. "
    "When answering questions about League of Legends tier lists or champion recommendations, "
    "use the champion tier list tool if not already loaded, "
    "and give specific champion names and reasoning based on the tier list. "
    "You can also inspect and answer questions about any documents or images uploaded by the user."
)

# -------------------------------------------------------------
# 1. TOOL FUNCTIONS (Execute locally on machine)
# -------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_champ_tier_list_base64() -> str:
    """Cache the base64 string in memory to avoid repeated disk reads."""
    image_path = os.path.join(os.path.dirname(__file__), "assets", "champ_tier_list.webp")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_champ_tier_list() -> list[dict]:
    """Returns the multimodal content block for the champion tier list image."""
    return [
        {"type": "text", "text": "champ_tier_list.webp"},
        {
            "type": "image",
            "mime_type": "image/webp",
            "data": _load_champ_tier_list_base64(),
        },
    ]

@lru_cache(maxsize=1)
def _load_resume_text() -> str:
    """Extract and cache resume text using PdfReader."""
    resume_path = os.path.join(os.path.dirname(__file__), "assets", "Vincent_Yuan_Resume.pdf")
    reader = PdfReader(resume_path)
    return "\n".join([page.extract_text() or "" for page in reader.pages])


def get_resume() -> list[dict]:
    """Returns the text content of Vincent Yuan's resume."""
    return [{"type": "text", "text": _load_resume_text()}]

# -------------------------------------------------------------
# 2. TOOL SCHEMAS & DISPATCH (Declarative JSON schema for Gemini)
# -------------------------------------------------------------
get_champ_tier_list_tool = {
    "type": "function",
    "name": "get_champ_tier_list",
    "description": "Returns the League of Legends champion tier list image. Call this tool when answering questions regarding champion tiers, meta rankings, tier lists, or strong picks if not already in context.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

get_resume_tool = {
    "type": "function",
    "name": "get_resume",
    "description": "Returns Vincent Yuan's resume text. Call this tool when answering questions about Vincent's experience, skills, education, or portfolio.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

TOOLS_SCHEMA = [get_champ_tier_list_tool, get_resume_tool]

TOOL_FUNCTIONS = {
    "get_champ_tier_list": get_champ_tier_list,
    "get_resume": get_resume,
}


def chat_with_agent(last_interaction_id: str | None, user_input) -> str | None:
    current_interaction_id = last_interaction_id
    current_input = user_input

    while True:
        try:
            stream = client.interactions.create(
                model=MODEL_NAME,
                input=current_input,
                system_instruction=SYSTEM_INSTRUCTION,
                store=True,
                stream=True,
                tools=TOOLS_SCHEMA,
                previous_interaction_id=current_interaction_id,
            )
        except Exception as e:
            print(f"[API Error: {e}]")
            return None

        current_calls = {}
        had_stream_error = False

        for event in stream:
            if event.event_type == "interaction.created":
                current_interaction_id = event.interaction.id
            elif event.event_type == "step.start":
                step = event.step
                if step.type == "function_call":
                    current_calls[event.index] = {
                        "id": step.id,
                        "name": step.name,
                        "arguments": "",
                    }
                    print(f"\n[Invoking tool: {step.name}...]", flush=True)
            elif event.event_type == "step.delta":
                if event.delta.type == "text":
                    print(event.delta.text, end="", flush=True)
                elif event.delta.type == "arguments_delta":
                    if event.index in current_calls:
                        current_calls[event.index]["arguments"] += event.delta.arguments
            elif event.event_type == "error":
                had_stream_error = True
                print(f"\n[Stream Error ({event.error.code}): {event.error.message}]")
            elif event.event_type == "interaction.completed":
                if not had_stream_error:
                    current_interaction_id = event.interaction.id

        if had_stream_error:
            print("\n")
            return None

        if not current_calls:
            print("\n")
            break

        # Execute requested tools and prepare function_result inputs
        function_results = []
        for call in current_calls.values():
            func_name = call["name"]
            func_id = call["id"]
            raw_args = call["arguments"]

            func = TOOL_FUNCTIONS.get(func_name)
            if not func:
                result_content = [{"type": "text", "text": f"Error: function {func_name} not found"}]
            else:
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                    result_content = func(**args) if args else func()
                except Exception as e:
                    result_content = [{"type": "text", "text": f"Error executing {func_name}: {e}"}]

            function_results.append({
                "type": "function_result",
                "name": func_name,
                "call_id": func_id,
                "result": result_content,
            })

        current_input = function_results

    return current_interaction_id


def upload_file_for_interaction(file_path: str) -> dict:
    """Uploads a local file using the Gemini Files API and returns the multimodal content block."""
    clean_path = file_path.strip().strip('"').strip("'")
    if not os.path.exists(clean_path):
        raise FileNotFoundError(f"File not found: {clean_path}")

    uploaded_file = client.files.upload(file=clean_path)
    mime = (uploaded_file.mime_type or "").lower()

    if mime.startswith("image/"):
        part_type = "image"
    elif "pdf" in mime or mime.startswith("text/") or "document" in mime:
        part_type = "document"
    elif mime.startswith("audio/"):
        part_type = "audio"
    elif mime.startswith("video/"):
        part_type = "video"
    else:
        part_type = "document"

    return {
        "type": part_type,
        "uri": uploaded_file.uri,
        "mime_type": uploaded_file.mime_type,
    }


def main():
    last_interaction_id = None
    print(f"=== Chat with {MODEL_NAME} (type 'quit' to stop, or '/upload <path> [prompt]' to upload a file) ===\n")
    try:
        while True:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["quit", "exit"]:
                break
            print()

            # Handle file upload via Gemini Files API
            if user_input.startswith("/upload"):
                parts = user_input.split(maxsplit=2)
                if len(parts) < 2:
                    print("[Usage: /upload <file_path> <optional prompt>]\n")
                    continue
                file_path = parts[1]
                prompt = parts[2] if len(parts) > 2 else "Please analyze this file."
                try:
                    print(f"[Uploading {file_path} via Files API...]", flush=True)
                    file_block = upload_file_for_interaction(file_path)
                    print(f"[Uploaded successfully: {file_block['uri']} ({file_block['mime_type']})]\n", flush=True)
                    current_payload = [
                        file_block,
                        {"type": "text", "text": prompt},
                    ]
                    last_interaction_id = chat_with_agent(last_interaction_id, current_payload)
                except Exception as e:
                    print(f"[Upload Error: {e}]\n")
                continue

            last_interaction_id = chat_with_agent(last_interaction_id, user_input)
    except KeyboardInterrupt:
        print("\nYou've terminated your session.")


if __name__ == "__main__":
    main()