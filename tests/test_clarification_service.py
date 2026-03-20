"""Tests for bot/services/clarification.py — answer extraction and model merging."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.clarification import (
    extract_answer,
    generate_clarification_questions,
    merge_extracted_answer,
    QUESTION_ORDER,
)
from tests.conftest import (
    SAMPLE_ASIS_MODEL,
    SAMPLE_CLARIFICATION_QUESTIONS,
    SAMPLE_EXTRACTED_ANSWER_METRICS,
    SAMPLE_EXTRACTED_ANSWER_SYSTEMS,
)


class TestMergeExtractedAnswer:
    """Test merge_extracted_answer for all field types."""

    def test_merge_metrics(self):
        """Metrics are added to correct stages and top-level."""
        model = {**SAMPLE_ASIS_MODEL, "stages": list(SAMPLE_ASIS_MODEL["stages"])}
        # Ensure stage_1 has empty metrics
        model["stages"] = [
            {**model["stages"][0], "metrics": []},
        ]

        result = merge_extracted_answer(model, "metrics", SAMPLE_EXTRACTED_ANSWER_METRICS)

        # Check stage-level metrics
        stage1 = result["stages"][0]
        assert len(stage1["metrics"]) == 2
        assert any("время оформления" in m for m in stage1["metrics"])

        # Check top-level metrics
        assert len(result["metrics"]) >= 2

    def test_merge_systems(self):
        """Systems are added to correct stages and top-level."""
        model = {**SAMPLE_ASIS_MODEL, "stages": [
            {**SAMPLE_ASIS_MODEL["stages"][0]},
            {
                "id": "stage_2", "name": "Настройка", "systems": [],
                "owner_role": "IT", "inputs": [], "outputs": [],
                "artifacts": [], "metrics": [], "sla": "", "pain_points": [],
                "handoff_to": None,
            },
        ]}

        result = merge_extracted_answer(model, "systems", SAMPLE_EXTRACTED_ANSWER_SYSTEMS)

        stage2 = result["stages"][1]
        assert "Active Directory" in stage2["systems"]
        assert "Active Directory" in result["systems"]

    def test_merge_roles(self):
        """Roles are set on correct stages and added to top-level."""
        model = {**SAMPLE_ASIS_MODEL, "stages": [
            {**SAMPLE_ASIS_MODEL["stages"][0], "owner_role": ""},
        ]}

        extracted = {"roles": [{"stage_id": "stage_1", "role": "HR-менеджер"}]}
        result = merge_extracted_answer(model, "roles", extracted)

        assert result["stages"][0]["owner_role"] == "HR-менеджер"
        assert "HR-менеджер" in result["roles"]

    def test_merge_operations(self):
        """New operations are appended as stages."""
        model = {**SAMPLE_ASIS_MODEL}
        extracted = {"operations": [
            {"name": "Проверка документов", "description": "Проверка комплектности"},
        ]}

        result = merge_extracted_answer(model, "operations", extracted)

        assert len(result["stages"]) == len(SAMPLE_ASIS_MODEL["stages"]) + 1
        new_stage = result["stages"][-1]
        assert new_stage["name"] == "Проверка документов"

    def test_merge_artifacts(self):
        """Artifacts are added to correct stages."""
        model = {**SAMPLE_ASIS_MODEL, "stages": [
            {**SAMPLE_ASIS_MODEL["stages"][0], "inputs": [], "outputs": []},
        ]}

        extracted = {"artifacts": [
            {"stage_id": "stage_1", "inputs": ["Паспорт", "СНИЛС"], "outputs": ["Приказ"]},
        ]}
        result = merge_extracted_answer(model, "artifacts", extracted)

        assert "Паспорт" in result["stages"][0]["inputs"]
        assert "СНИЛС" in result["stages"][0]["inputs"]
        assert "Приказ" in result["stages"][0]["outputs"]

    def test_merge_no_duplicates(self):
        """Duplicate values are not added."""
        model = {**SAMPLE_ASIS_MODEL, "stages": [
            {**SAMPLE_ASIS_MODEL["stages"][0], "systems": ["1С"]},
        ], "systems": ["1С"]}

        extracted = {"systems": [{"stage_id": "stage_1", "system": "1С"}]}
        result = merge_extracted_answer(model, "systems", extracted)

        assert result["stages"][0]["systems"].count("1С") == 1
        assert result["systems"].count("1С") == 1


class TestQuestionOrder:
    """Test QUESTION_ORDER constant."""

    def test_order(self):
        assert QUESTION_ORDER == ["operations", "metrics", "roles", "systems", "artifacts"]


class TestExtractAnswer:
    """Test extract_answer LLM call."""

    @pytest.mark.asyncio
    async def test_extract_answer_calls_llm(self):
        """extract_answer calls LLM with correct context."""
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_EXTRACTED_ANSWER_METRICS, ensure_ascii=False),
        ) as mock_chat:
            result = await extract_answer(
                "metrics",
                "Какие метрики?",
                "Время — 1 день",
                SAMPLE_ASIS_MODEL,
            )

        mock_chat.assert_called_once()
        assert "metrics" in result
        assert len(result["metrics"]) == 2

    @pytest.mark.asyncio
    async def test_extract_answer_handles_invalid_json(self):
        """extract_answer returns empty dict on invalid JSON."""
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value="not valid json",
        ):
            result = await extract_answer("metrics", "Q?", "A", {})

        assert result == {}
