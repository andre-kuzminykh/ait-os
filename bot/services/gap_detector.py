"""Gap detection and follow-up question generation (LLM Call 2).

Questions are structured by stage: for each stage we check that
role, system, metrics, and artifacts (input/output) are filled.
We also check if the list of stages itself seems complete.
"""

import json
import logging

from bot.prompts import load_prompt
from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("gap_detector")


async def detect_gaps(process_name: str, asis_model: dict) -> dict:
    """Detect missing fields and generate follow-up questions.

    Returns dict with completeness_score and gaps list.
    """
    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Текущая модель AS-IS:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    response = await chat(SYSTEM_PROMPT, user_msg)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse gap detector JSON: %s", text[:500])
        return {"completeness_score": 0.0, "gaps": []}
