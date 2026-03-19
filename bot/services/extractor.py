"""AS-IS model extraction from raw user inputs (LLM Call 1)."""

import json
import logging

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — аналитик бизнес-процессов. Тебе передают текстовые записи интервью \
с сотрудниками компании. Твоя задача — извлечь структурированное описание \
текущего (AS-IS) процесса.

Верни ТОЛЬКО валидный JSON (без markdown-обёртки) со следующей структурой:
{
  "goal": "цель процесса",
  "summary": "краткое описание процесса",
  "triggers": ["список триггеров"],
  "inputs": ["входные данные/документы"],
  "outputs": ["выходные данные/результаты"],
  "stages": [
    {
      "id": "stage_1",
      "name": "Название этапа",
      "description": "Описание этапа",
      "owner_role": "роль ответственного",
      "systems": ["системы"],
      "inputs": ["входы"],
      "outputs": ["выходы"],
      "artifacts": ["артефакты"],
      "metrics": ["метрики"],
      "sla": "SLA если известно",
      "pain_points": ["проблемы"],
      "handoff_to": "следующий этап или роль"
    }
  ],
  "roles": ["все роли"],
  "systems": ["все системы"],
  "artifacts": ["все артефакты"],
  "metrics": ["все метрики"],
  "pain_points": ["общие проблемы"],
  "handoffs": ["передачи между этапами"]
}

Если информация не была упомянута, ставь пустой список [] или null. \
Не выдумывай данные. Используй только то, что сказано в интервью.\
"""


async def extract_asis_model(
    process_name: str,
    raw_texts: list[str],
    existing_model_json: str | None = None,
) -> dict:
    """Extract or update structured AS-IS model from interview texts.

    Returns a dict matching the JSON schema above.
    """
    parts = [f"Процесс: {process_name}\n"]

    if existing_model_json:
        parts.append(
            "Текущая модель (обнови и дополни на основе новых данных):\n"
            f"{existing_model_json}\n"
        )

    parts.append("Записи интервью:\n")
    for i, text in enumerate(raw_texts, 1):
        parts.append(f"--- Запись {i} ---\n{text}\n")

    user_msg = "\n".join(parts)

    response = await chat(SYSTEM_PROMPT, user_msg)

    # Parse JSON from response, stripping markdown fences if present
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse extractor JSON: %s", text[:500])
        return {}
