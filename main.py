import os
from dotenv import load_dotenv
from google import genai

def main():
    load_dotenv()
    client = genai.Client() # automatically reads GEMINI_API_KEY from environment
    MODEL_NAME = "gemini-3.6-flash"
    SYSTEM_INSTRUCTION = "You are a helpful portfolio assistant."

    print(f"--- Chat with {MODEL_NAME} (type 'quit' or 'exit' or 'CTRL + D' to stop) ---\n")

    last_interaction_id = None

    try:
        while True:
            user_input = input("You: ")
            if user_input.lower() in ['quit', 'exit']:
                break

            interaction = client.interactions.create(
                model=MODEL_NAME,
                input=user_input,
                system_instruction=SYSTEM_INSTRUCTION,
                store=True,
                #stream=True,
                previous_interaction_id=last_interaction_id
            )

            print(f"\nGemini: {interaction.output_text}\n")

            last_interaction_id = interaction.id

    except KeyboardInterrupt:
        print("You've terminated your session")

if __name__ == "__main__":
    main()