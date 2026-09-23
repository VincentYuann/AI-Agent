from config import MODEL_NAME
from files import upload_file_for_interaction
from agent import chat_with_agent


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