"""Loads settings from .env into a single Settings object."""
import os
from dotenv import load_dotenv

load_dotenv()


def _list_from_env(key: str) -> list[str]:
    raw = os.getenv(key, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    # No Reddit credentials: this tool is read-only. It fetches public posts
    # via Reddit's public RSS feeds (see fetch_scraper.py) — no API app, no
    # login — and drafts replies for a human to review and post manually.

    # LLM provider switch: "gemini" (OpenAI-compatible) or "bedrock" (AWS).
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

    # --- Gemini (OpenAI-compatible endpoint) ---
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash")
    LLM_BASE_URL = os.getenv(
        "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    # --- AWS Bedrock (uses AWS CLI / boto3 credentials, not an API key) ---
    # Model IDs take an "anthropic." prefix; current Claude models use a
    # cross-region inference profile, e.g. "us.anthropic.claude-sonnet-5".
    BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-5")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Targeting
    TARGET_SUBREDDITS = _list_from_env("TARGET_SUBREDDITS")
    TARGET_KEYWORDS = _list_from_env("TARGET_KEYWORDS")

    # Product
    PRODUCT_NAME = os.getenv("PRODUCT_NAME", "Our product")
    PRODUCT_URL = os.getenv("PRODUCT_URL", "")
    PRODUCT_DESCRIPTION = os.getenv("PRODUCT_DESCRIPTION", "")

    # Runtime
    POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    DB_PATH = os.getenv("DB_PATH", "data/agent.db")


settings = Settings()
