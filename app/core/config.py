import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "ERP Chatbot")
    DEBUG: bool = os.getenv("DEBUG", "False") == "True"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")

    # ✅ ADD THIS BLOCK (IMPORTANT FIX)
    DB_CONTEXT = {
        "saminc": {
            "frozen_year": 2023,
            "mode": "snapshot",
            "date_anchor": "2023-12-31"
        }
    }

    DEFAULT_DB: str = "saminc"

# Create a single settings instance
settings = Settings()