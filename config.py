import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Automatically reads GEMINI_API_KEY from environment
client = genai.Client()

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

