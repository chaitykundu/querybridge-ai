import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "ERP Chatbot")
    DEBUG: bool = os.getenv("DEBUG", "False") == "True"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")

# Create a single settings instance
settings = Settings()