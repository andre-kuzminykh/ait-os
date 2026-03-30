"""Mermaid diagram generation (LLM Call 4)."""

import json
import logging
import re

from bot.prompts import load_prompt
from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("mermaid")


def validate_mermaid(code: str) -> bool:
    """Basic validation that Mermaid code looks syntactically reasonable."""
    code = code.strip()
    if not code:
        return False
    first_line = code.split("\n")[0].strip().lower()
    valid_starts = ("flowchart", "graph", "sequencediagram", "gantt", "classDiagram")
    return any(first_line.startswith(s.lower()) for s in valid_starts)


def count_rect_nodes(code: str) -> int:
    """Count rectangular nodes (ID[Label]) in Mermaid flowchart code.

    Diamonds {Label} are not counted — they are decision points, not stages.
    """
    # Match node definitions like A[Text] — first occurrence defines the node
    return len(re.findall(r'\b[A-Za-z]\w*\[', code))


def sanitize_mermaid(code: str) -> str:
    """Remove markdown fences, fix quotes, and clean up Mermaid code."""
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```\w*\n?", "", code)
        code = re.sub(r"\n?```$", "", code)
    code = code.strip()

    # Fix common issues that break Mermaid rendering:
    # 1. Remove quotes around node labels: A["Text"] → A[Text]
    code = re.sub(r'\[\"([^"]*)\"\]', r'[\1]', code)
    code = re.sub(r"\[\'([^']*)\'\]", r'[\1]', code)
    # 2. Same for rhombus nodes: D{"Text?"} → D{Text?}
    code = re.sub(r'\{\"([^"]*)\"\}', r'{\1}', code)
    code = re.sub(r"\{\'([^']*)\'\}", r'{\1}', code)
    # 3. Replace special chars inside node labels that break rendering
    def _clean_label(m: re.Match) -> str:
        bracket, content, close = m.group(1), m.group(2), m.group(3)
        content = content.replace("&", "и")
        content = content.replace("#", "")
        content = content.replace("<", "")
        content = content.replace(">", "")
        # Remove parentheses that Mermaid may misinterpret as shape syntax
        content = content.replace("(", "")
        content = content.replace(")", "")
        return f"{bracket}{content}{close}"

    code = re.sub(r'(\[)([^\]]+)(\])', _clean_label, code)
    code = re.sub(r'(\{)([^}]+)(\})', _clean_label, code)

    return code


async def generate_mermaid(process_name: str, asis_model: dict) -> str:
    """Generate Mermaid diagram code from AS-IS model.

    Returns Mermaid code string or empty string on failure.
    """
    stages = asis_model.get("stages", [])
    stage_names = [s.get("name", f"Этап {i+1}") for i, s in enumerate(stages)]
    stage_list = "\n".join(f"  {i+1}. {name}" for i, name in enumerate(stage_names))

    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Количество этапов: {len(stages)}\n"
        f"Этапы (именно столько блоков должно быть на диаграмме):\n{stage_list}\n\n"
        f"Модель:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    expected_blocks = len(stages)

    for attempt in range(3):
        response = await chat(SYSTEM_PROMPT, user_msg)
        code = sanitize_mermaid(response)

        if not validate_mermaid(code):
            logger.warning(
                "Mermaid validation failed (attempt %d): %s",
                attempt + 1, code[:200],
            )
            if attempt == 0:
                user_msg += (
                    "\n\nПредыдущая попытка не прошла валидацию. "
                    "Сделай диаграмму проще, используй только flowchart TD "
                    "с простыми узлами и стрелками."
                )
            continue

        # Check block count matches stage count
        actual_blocks = count_rect_nodes(code)
        if expected_blocks > 0 and actual_blocks != expected_blocks:
            logger.warning(
                "Mermaid block count mismatch (attempt %d): "
                "expected %d stages, got %d blocks",
                attempt + 1, expected_blocks, actual_blocks,
            )
            user_msg += (
                f"\n\nОШИБКА: в диаграмме {actual_blocks} прямоугольных блоков, "
                f"а должно быть ровно {expected_blocks} (по числу этапов). "
                f"Этапы: {', '.join(stage_names)}. "
                "Создай ровно по одному блоку на каждый этап. "
                "Не добавляй блоки Начало/Конец/Готово."
            )
            continue

        return code

    logger.error("Mermaid generation failed after retries")
    return ""
