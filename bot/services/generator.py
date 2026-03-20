"""AS-IS narrative generation (LLM Call 3)."""

import json
import logging

from bot.prompts import load_prompt
from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("generator")


async def generate_narrative(process_name: str, asis_model: dict) -> dict:
    """Generate narrative HTML sections from the AS-IS model.

    Returns dict with HTML fragments for each section.
    """
    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Модель AS-IS:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    response = await chat(SYSTEM_PROMPT, user_msg, max_tokens=8192)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse narrative JSON: %s", text[:500])
        return {"title": process_name, "summary": "Ошибка генерации описания."}
