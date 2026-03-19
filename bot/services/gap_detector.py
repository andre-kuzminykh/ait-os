"""Gap detection and follow-up question generation (LLM Call 2)."""

import json
import logging

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — аналитик бизнес-процессов. Тебе дана структурированная модель процесса AS-IS. \
Проверь, какие важные данные отсутствуют или недостаточно описаны.

Для каждого пропуска сформулируй один конкретный, атомарный уточняющий вопрос.

Верни ТОЛЬКО валидный JSON (без markdown-обёртки):
{
  "completeness_score": 0.0-1.0,
  "gaps": [
    {
      "stage_id": "stage_1 или null если вопрос про процесс в целом",
      "field_type": "roles|systems|artifacts|metrics|trigger|output|sla_timing|handoff|decision_point|goal|input|pain_points",
      "question": "Конкретный вопрос на русском",
      "confidence": 0.0-1.0
    }
  ]
}

Приоритизируй вопросы по важности. Максимум 5 вопросов за раз. \
Вопросы должны быть короткими, понятными и легко отвечаемыми в одном сообщении.\
"""


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
