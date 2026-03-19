"""Mermaid diagram generation (LLM Call 4)."""

import json
import logging
import re

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — специалист по визуализации бизнес-процессов. \
Тебе дана структурированная модель процесса AS-IS. \
Создай Mermaid-диаграмму (flowchart TD) для этого процесса.

Правила:
- Используй flowchart TD (сверху вниз).
- Каждый этап — отдельный узел.
- Покажи переходы между этапами.
- Добавь роли как подписи, если они есть.
- Добавь условия/развилки, если есть decision points.
- Узлы и подписи на русском.
- Не используй специальные символы, которые ломают Mermaid-синтаксис.

Верни ТОЛЬКО код Mermaid, без обёрток ``` и без пояснений.\
"""


def validate_mermaid(code: str) -> bool:
    """Basic validation that Mermaid code looks syntactically reasonable."""
    code = code.strip()
    if not code:
        return False
    first_line = code.split("\n")[0].strip().lower()
    valid_starts = ("flowchart", "graph", "sequencediagram", "gantt", "classDiagram")
    return any(first_line.startswith(s.lower()) for s in valid_starts)


def sanitize_mermaid(code: str) -> str:
    """Remove markdown fences and clean up Mermaid code."""
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```\w*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)
    return code.strip()


async def generate_mermaid(process_name: str, asis_model: dict) -> str:
    """Generate Mermaid diagram code from AS-IS model.

    Returns Mermaid code string or empty string on failure.
    """
    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Модель:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    for attempt in range(2):
        response = await chat(SYSTEM_PROMPT, user_msg)
        code = sanitize_mermaid(response)

        if validate_mermaid(code):
            return code

        logger.warning(
            "Mermaid validation failed (attempt %d): %s", attempt + 1, code[:200]
        )
        # Retry with simplified request
        if attempt == 0:
            user_msg += (
                "\n\nПредыдущая попытка не прошла валидацию. "
                "Сделай диаграмму проще, используй только flowchart TD "
                "с простыми узлами и стрелками."
            )

    logger.error("Mermaid generation failed after retries")
    return ""
