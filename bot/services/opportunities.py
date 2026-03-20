"""Automation opportunity generation (LLM Call 5)."""

from __future__ import annotations

import json
import logging

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — консультант по цифровой трансформации. \
Тебе дана модель текущего бизнес-процесса AS-IS. \
Проанализируй болевые точки, ручные операции, узкие места, \
передачи между этапами и предложи конкретные возможности автоматизации.

Верни ТОЛЬКО валидный JSON (без markdown-обёртки):
{
  "opportunities": [
    {
      "title": "Краткое название возможности",
      "stage_id": "stage_1 или null",
      "type": "ai|rule_based|integration|analytics|monitoring",
      "problem": "Какую проблему решает",
      "description": "Что именно можно автоматизировать",
      "expected_benefit": "Ожидаемый эффект"
    }
  ]
}

Правила:
- Каждая возможность должна быть понятна бизнес-пользователю.
- Не дублируй похожие возможности.
- Приоритизируй по потенциальному эффекту.
- Минимум 2, максимум 8 возможностей.\
"""


async def generate_opportunities(process_name: str, asis_model: dict) -> list[dict]:
    """Generate automation opportunities based on AS-IS model.

    Returns list of opportunity dicts.
    """
    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Модель AS-IS:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    response = await chat(SYSTEM_PROMPT, user_msg)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
        return data.get("opportunities", [])
    except json.JSONDecodeError:
        logger.error("Failed to parse opportunities JSON: %s", text[:500])
        return []
