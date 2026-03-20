"""Clarification question generation and answer extraction (LLM Calls 2a, 2b).

Replaces gap_detector with a structured 5-question flow:
1. Operations/steps completeness (LLM decides if needed)
2. Metrics and values (where missing)
3. Roles (where missing)
4. Systems (where missing)
5. Artifacts (where missing)

Each question includes LLM-suggested answers. User responds via text/voice
or skips. Answers are extracted by LLM and merged into the AS-IS model.
"""

import json
import logging

from bot.prompts import load_prompt
from bot.services.llm import chat

logger = logging.getLogger(__name__)

QUESTIONS_PROMPT = load_prompt("clarification_questions")
ANSWER_PROMPT = load_prompt("answer_extractor")

# Fixed order of question types
QUESTION_ORDER = ["operations", "metrics", "roles", "systems", "artifacts"]


async def generate_clarification_questions(
    process_name: str, asis_model: dict,
) -> list[dict]:
    """Generate up to 5 structured clarification questions.

    Returns list of dicts with keys: field_type, question, suggestions.
    Only includes questions where include=True (fields are actually empty).
    """
    user_msg = (
        f"Процесс: {process_name}\n\n"
        f"Текущая модель AS-IS:\n{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    response = await chat(QUESTIONS_PROMPT, user_msg)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse clarification questions JSON: %s", text[:500])
        return []

    questions = data.get("questions", [])

    # Filter to only included questions, maintain order
    result = []
    for q in questions:
        if q.get("include", False):
            result.append({
                "field_type": q.get("field_type", ""),
                "question": q.get("question", ""),
                "suggestions": q.get("suggestions", []),
            })

    return result


async def extract_answer(
    field_type: str,
    question: str,
    user_answer: str,
    asis_model: dict,
) -> dict:
    """Extract structured data from user's answer to a clarification question.

    Returns dict with extracted values keyed by field_type.
    """
    user_msg = (
        f"Тип вопроса (field_type): {field_type}\n\n"
        f"Вопрос, который был задан:\n{question}\n\n"
        f"Ответ пользователя:\n{user_answer}\n\n"
        f"Текущая модель AS-IS (для контекста):\n"
        f"{json.dumps(asis_model, ensure_ascii=False, indent=2)}"
    )

    response = await chat(ANSWER_PROMPT, user_msg)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse answer extraction JSON: %s", text[:500])
        return {}


def merge_extracted_answer(asis_model: dict, field_type: str, extracted: dict) -> dict:
    """Merge extracted answer data into the AS-IS model.

    Returns updated model dict.
    """
    model = {**asis_model}
    stages = list(model.get("stages", []))

    if field_type == "operations":
        new_ops = extracted.get("operations", [])
        for op in new_ops:
            new_stage = {
                "id": f"stage_{len(stages) + 1}",
                "name": op.get("name", ""),
                "description": op.get("description", ""),
                "owner_role": "",
                "systems": [],
                "inputs": [],
                "outputs": [],
                "artifacts": [],
                "metrics": [],
                "sla": "",
                "pain_points": [],
                "handoff_to": None,
            }
            stages.append(new_stage)
        model["stages"] = stages

    elif field_type == "metrics":
        new_metrics = extracted.get("metrics", [])
        for m in new_metrics:
            stage_id = m.get("stage_id")
            for stage in stages:
                if stage.get("id") == stage_id:
                    stage_metrics = stage.get("metrics", [])
                    metric_entry = m.get("metric_name", "")
                    if m.get("metric_value"):
                        metric_entry += f": {m['metric_value']}"
                    if metric_entry and metric_entry not in stage_metrics:
                        stage_metrics.append(metric_entry)
                    stage["metrics"] = stage_metrics
                    break
        model["stages"] = stages
        # Also update top-level metrics
        all_metrics = model.get("metrics", [])
        for m in new_metrics:
            entry = m.get("metric_name", "")
            if entry and entry not in all_metrics:
                all_metrics.append(entry)
        model["metrics"] = all_metrics

    elif field_type == "roles":
        new_roles = extracted.get("roles", [])
        for r in new_roles:
            stage_id = r.get("stage_id")
            role = r.get("role", "")
            for stage in stages:
                if stage.get("id") == stage_id:
                    stage["owner_role"] = role
                    break
            # Update top-level roles
            all_roles = model.get("roles", [])
            if role and role not in all_roles:
                all_roles.append(role)
            model["roles"] = all_roles
        model["stages"] = stages

    elif field_type == "systems":
        new_systems = extracted.get("systems", [])
        for s in new_systems:
            stage_id = s.get("stage_id")
            system = s.get("system", "")
            for stage in stages:
                if stage.get("id") == stage_id:
                    stage_systems = stage.get("systems", [])
                    if system and system not in stage_systems:
                        stage_systems.append(system)
                    stage["systems"] = stage_systems
                    break
            # Update top-level systems
            all_systems = model.get("systems", [])
            if system and system not in all_systems:
                all_systems.append(system)
            model["systems"] = all_systems
        model["stages"] = stages

    elif field_type == "artifacts":
        new_artifacts = extracted.get("artifacts", [])
        for a in new_artifacts:
            stage_id = a.get("stage_id")
            for stage in stages:
                if stage.get("id") == stage_id:
                    for inp in a.get("inputs", []):
                        if inp not in stage.get("inputs", []):
                            stage.setdefault("inputs", []).append(inp)
                    for out in a.get("outputs", []):
                        if out not in stage.get("outputs", []):
                            stage.setdefault("outputs", []).append(out)
                    break
            # Update top-level artifacts
            all_artifacts = model.get("artifacts", [])
            for inp in a.get("inputs", []):
                if inp not in all_artifacts:
                    all_artifacts.append(inp)
            for out in a.get("outputs", []):
                if out not in all_artifacts:
                    all_artifacts.append(out)
            model["artifacts"] = all_artifacts
        model["stages"] = stages

    return model
