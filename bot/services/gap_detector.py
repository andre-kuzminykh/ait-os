"""Gap detection and follow-up question generation (LLM Call 2).

Questions are structured by stage: for each stage we check that
role, system, metrics, and artifacts (input/output) are filled.
We also check if the list of stages itself seems complete.
"""

import json
import logging

from bot.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты — аналитик бизнес-процессов. Тебе дана структурированная модель процесса AS-IS.

Твоя задача — проверить каждый этап (stage) и определить, какие данные отсутствуют.
По каждому этапу должны быть заполнены:
1. Роль (owner_role) — кто выполняет этот шаг
2. Система (systems) — в какой системе / где это происходит
3. Метрики (metrics) — какие метрики / KPI / SLA отслеживаются
4. Артефакты-входы (inputs) — какой документ/данные приходят из предыдущего шага
5. Артефакты-выходы (outputs) — какой документ/данные уходят в следующий шаг

Также проверь:
- Достаточно ли этапов? Нет ли пропущенных шагов между существующими?
- Указана ли цель процесса и триггер?

Правила генерации вопросов:
- Спрашивай ТОЛЬКО о том, что реально пусто или отсутствует в модели.
- НЕ спрашивай о том, что уже заполнено.
- Группируй вопросы по приоритету:
  1. Пропущенные шаги (если кажется что между этапами есть разрыв)
  2. Роли — кто выполняет шаг
  3. Системы — где это происходит
  4. Метрики — как измеряется
  5. Артефакты — что на входе и выходе каждого шага
- Максимум 5 вопросов за раз, минимум вопросов — только о реально пустых полях.
- Вопросы должны быть короткими и конкретными.

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

Формула completeness_score:
- Посчитай для каждого этапа: есть ли role, system, metric, input-artifact, output-artifact
- completeness = (заполненных полей) / (всего полей по всем этапам)
- Если этапов нет вообще — score = 0.1 максимум.
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
