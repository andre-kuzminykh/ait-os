"""Prompt loader — reads .txt prompt files from this directory."""

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """Load prompt text from ``bot/prompts/<name>.txt``."""
    path = _DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()
