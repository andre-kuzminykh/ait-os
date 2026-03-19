"""Tests for FR-9..FR-10: Gap Detection.

FR-9   System must detect missing or low-confidence fields at process and stage level.
FR-10  Gap detection must classify missing data by type.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.gap_detector import detect_gaps, SYSTEM_PROMPT
from bot.states import GapFieldType
from tests.conftest import SAMPLE_ASIS_MODEL, SAMPLE_GAP_RESULT


# ============================================================================
# FR-9: Detect missing or low-confidence fields
# ============================================================================


class TestFR9_GapDetection:
    """FR-9: System must detect missing or low-confidence fields."""

    @pytest.mark.asyncio
    async def test_gap_detector_returns_completeness_score(self):
        """FR-9.1: Gap detector returns a completeness_score between 0 and 1."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Онбординг", SAMPLE_ASIS_MODEL)

        assert "completeness_score" in result
        assert 0.0 <= result["completeness_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_gap_detector_returns_gaps_list(self):
        """FR-9.2: Gap detector returns a list of gaps."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Онбординг", SAMPLE_ASIS_MODEL)

        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        assert len(result["gaps"]) > 0

    @pytest.mark.asyncio
    async def test_gap_has_question_text(self):
        """FR-9.3: Each gap includes a specific question text."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        for gap in result["gaps"]:
            assert "question" in gap
            assert len(gap["question"]) > 5

    @pytest.mark.asyncio
    async def test_gap_has_stage_reference(self):
        """FR-9.4: Gaps can reference a specific stage or be process-level (null)."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        has_stage_level = any(g["stage_id"] is not None for g in result["gaps"])
        has_process_level = any(g["stage_id"] is None for g in result["gaps"])
        # Should have at least one type
        assert has_stage_level or has_process_level

    @pytest.mark.asyncio
    async def test_gap_detector_handles_invalid_json(self):
        """FR-9.5: Gap detector returns defaults on invalid LLM response."""
        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value="broken"):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        assert result["completeness_score"] == 0.0
        assert result["gaps"] == []

    @pytest.mark.asyncio
    async def test_gap_has_confidence_score(self):
        """FR-9.6: Each gap has a confidence score."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        for gap in result["gaps"]:
            assert "confidence" in gap
            assert 0.0 <= gap["confidence"] <= 1.0


# ============================================================================
# FR-10: Gap detection classifies missing data by type
# ============================================================================


class TestFR10_GapClassification:
    """FR-10: Gap detection must classify missing data by type."""

    @pytest.mark.asyncio
    async def test_gap_has_field_type(self):
        """FR-10.1: Each gap includes a field_type classification."""
        llm_response = json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        for gap in result["gaps"]:
            assert "field_type" in gap

    @pytest.mark.asyncio
    async def test_field_types_match_enum(self):
        """FR-10.2: Prompt requests field_type values matching GapFieldType enum."""
        enum_values = [e.value for e in GapFieldType]
        # Check that prompt references the field types
        for val in ["roles", "systems", "artifacts", "metrics", "trigger",
                     "output", "sla_timing", "handoff", "decision_point"]:
            assert val in SYSTEM_PROMPT, f"Missing field type '{val}' in prompt"

    @pytest.mark.asyncio
    async def test_gap_field_type_enum_complete(self):
        """FR-10.3: GapFieldType enum covers all required classification types."""
        required = {
            "roles", "systems", "artifacts", "metrics",
            "trigger", "output", "sla_timing", "handoff",
            "decision_point",
        }
        enum_values = {e.value for e in GapFieldType}
        assert required.issubset(enum_values)

    @pytest.mark.asyncio
    async def test_different_gap_types_returned(self):
        """FR-10.4: Detector can return gaps of different types."""
        multi_type_result = {
            "completeness_score": 0.4,
            "gaps": [
                {"stage_id": "stage_1", "field_type": "metrics", "question": "Q1?", "confidence": 0.3},
                {"stage_id": None, "field_type": "roles", "question": "Q2?", "confidence": 0.4},
                {"stage_id": "stage_2", "field_type": "sla_timing", "question": "Q3?", "confidence": 0.5},
            ],
        }
        llm_response = json.dumps(multi_type_result, ensure_ascii=False)

        with patch("bot.services.gap_detector.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await detect_gaps("Тест", SAMPLE_ASIS_MODEL)

        types = {g["field_type"] for g in result["gaps"]}
        assert len(types) >= 2
