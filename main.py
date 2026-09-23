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
    "You are a helpful portfolio assistant. When answering questions about League of Legends "
    "tier lists or champion recommendations, use the champion tier list tool if not already loaded, "
    "and give specific champion names and reasoning based on the tier list."
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
def _load_resume_pdf() -> str:
    uploaded_file = client.files.upload(file="file.pdf")

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

TOOLS_SCHEMA = [get_champ_tier_list_tool]

TOOL_FUNCTIONS = {
    "get_champ_tier_list": get_champ_tier_list,
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
            if "404" in str(e) or "not_found" in str(e).lower():
                print("[Previous session not found. Starting a fresh turn...]\n")
                current_interaction_id = None
                stream = client.interactions.create(
                    model=MODEL_NAME,
                    input=current_input,
                    system_instruction=SYSTEM_INSTRUCTION,
                    store=True,
                    stream=True,
                    tools=TOOLS_SCHEMA,
                    previous_interaction_id=None,
                )
            else:
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
                    output = func(**args) if args else func()

                    # Modular result packaging
                    if isinstance(output, list):
                        result_content = output
                    elif isinstance(output, dict):
                        result_content = [{"type": "text", "text": json.dumps(output)}]
                    else:
                        result_content = [{"type": "text", "text": str(output)}]
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


def main():
    last_interaction_id = None
    print(f"=== Chat with {MODEL_NAME} (type 'quit' or 'exit' to stop) ===\n")
    try:
        while True:
            user_input = input("You: ")
            if user_input.strip().lower() in ["quit", "exit"]:
                break
            print()

            last_interaction_id = chat_with_agent(last_interaction_id, user_input)
    except KeyboardInterrupt:
        print("\nYou've terminated your session.")


if __name__ == "__main__":
    main()