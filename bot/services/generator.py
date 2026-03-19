"""AS-IS narrative generation (LLM Call 3)."""

import json
import logging

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — технический писатель. Тебе дана структурированная модель бизнес-процесса AS-IS. \
Напиши понятное, структурированное описание процесса на русском языке в формате HTML-фрагментов.

Верни ТОЛЬКО валидный JSON (без markdown-обёртки) со следующей структурой:
{
  "title": "Название процесса",
  "goal": "Цель процесса — один абзац",
  "summary": "Краткое описание процесса — 2-3 предложения",
  "triggers_html": "<ul>...</ul>",
  "inputs_html": "<ul>...</ul>",
  "outputs_html": "<ul>...</ul>",
  "roles_html": "<ul>...</ul> или таблица",
  "systems_html": "<ul>...</ul>",
  "artifacts_html": "<ul>...</ul>",
  "stages_html": "HTML описание этапов процесса с деталями по каждому этапу",
  "metrics_html": "<ul>...</ul> или таблица метрик по этапам",
  "pain_points_html": "<ul>...</ul>",
  "automation_candidates_html": "<ul>...</ul> краткий блок потенциальных точек автоматизации"
}

Стиль:
- Лаконичный, деловой.
- Используй списки и таблицы для наглядности.
- HTML без внешних стилей, только чистый HTML.\
"""


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
