import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Initialize Gemini Client (automatically reads GEMINI_API_KEY from environment)
client = genai.Client()

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Explain how AI works in a few words"
)
print(interaction.output_text)

def main():
    print("Hello from ai-agent!")

if __name__ == "__main__":
    main()