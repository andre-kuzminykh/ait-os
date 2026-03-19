"""Application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"
)

BASE_DIR = Path(__file__).resolve().parent.parent
PAGES_DIR = Path(os.environ.get("PAGES_DIR", str(BASE_DIR / "pages")))
PAGES_BASE_URL: str = os.environ.get("PAGES_BASE_URL", "http://localhost:8080/pages")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# LLM settings
LLM_MODEL: str = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

# Completeness threshold (0.0 – 1.0) to trigger AS-IS generation
COMPLETENESS_THRESHOLD: float = float(
    os.environ.get("COMPLETENESS_THRESHOLD", "0.6")
)

# Maximum follow-up questions before forcing generation
MAX_FOLLOWUP_QUESTIONS: int = int(os.environ.get("MAX_FOLLOWUP_QUESTIONS", "15"))
