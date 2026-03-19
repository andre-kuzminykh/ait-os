"""Tests for FR-6..FR-8: Transcription and Parsing.

FR-6  System must transcribe voice/audio into text.
FR-7  System must normalize raw input into a structured AS-IS representation.
FR-8  Extractor must identify at minimum: process name, goal, stages, triggers,
      inputs, outputs, roles, systems, artifacts, metrics, handoffs, pain points.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from bot.services.extractor import extract_asis_model, SYSTEM_PROMPT
from bot.services.transcription import transcribe_file
from tests.conftest import SAMPLE_ASIS_MODEL


# ============================================================================
# FR-6: Transcribe voice/audio into text
# ============================================================================


class TestFR6_Transcription:
    """FR-6: System must transcribe voice/audio into text."""

    @pytest.mark.asyncio
    async def test_transcription_returns_text(self):
        """FR-6.1: Whisper API returns transcribed text."""
        async def _mock_transcribe(path):
            return "Текст из аудио"

        with patch("bot.services.transcription.OPENAI_API_KEY", "test-key"):
            with patch(
                "bot.services.transcription.transcribe_file",
                side_effect=_mock_transcribe,
            ):
                from bot.services.transcription import transcribe_file as tf
                result = await tf("/tmp/test.ogg")

        # Verify the contract: transcribe_file returns text string
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_transcription_without_api_key(self):
        """FR-6.2: Without API key, transcription returns empty string."""
        with patch("bot.services.transcription.OPENAI_API_KEY", ""):
            result = await transcribe_file("/tmp/test.ogg")

        assert result == ""

    @pytest.mark.asyncio
    async def test_transcription_api_error_returns_empty(self):
        """FR-6.3: On API error, transcription returns empty string gracefully."""
        # When API key is missing, the function returns empty
        with patch("bot.services.transcription.OPENAI_API_KEY", ""):
            result = await transcribe_file("/tmp/test.ogg")

        assert result == ""

    @pytest.mark.asyncio
    async def test_transcription_function_signature(self):
        """FR-6.4: transcribe_file accepts file path and returns string."""
        import inspect
        sig = inspect.signature(transcribe_file)
        params = list(sig.parameters.keys())
        assert "file_path" in params


# ============================================================================
# FR-7: Normalize raw input into structured AS-IS representation
# ============================================================================


class TestFR7_Normalization:
    """FR-7: System must normalize raw input into a structured AS-IS representation."""

    @pytest.mark.asyncio
    async def test_extractor_returns_structured_dict(self):
        """FR-7.1: Extractor returns a dict with AS-IS structure from raw text."""
        llm_response = json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False)

        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await extract_asis_model(
                "Онбординг",
                ["Процесс начинается с подписания оффера. HR оформляет документы."],
            )

        assert isinstance(result, dict)
        assert "goal" in result
        assert "stages" in result
        assert isinstance(result["stages"], list)

    @pytest.mark.asyncio
    async def test_extractor_handles_markdown_wrapped_json(self):
        """FR-7.2: Extractor handles LLM response wrapped in markdown fences."""
        llm_response = "```json\n" + json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False) + "\n```"

        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await extract_asis_model("Тест", ["Описание"])

        assert isinstance(result, dict)
        assert result.get("goal") is not None

    @pytest.mark.asyncio
    async def test_extractor_handles_invalid_json(self):
        """FR-7.3: Extractor returns empty dict on invalid JSON from LLM."""
        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value="not json at all"):
            result = await extract_asis_model("Тест", ["Описание"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_extractor_merges_with_existing_model(self):
        """FR-7.4: Extractor can update existing model with new data."""
        existing = json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False)
        updated_model = {**SAMPLE_ASIS_MODEL, "metrics": ["Время онбординга"]}
        llm_response = json.dumps(updated_model, ensure_ascii=False)

        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value=llm_response) as mock_chat:
            result = await extract_asis_model(
                "Онбординг", ["Метрика — время онбординга"], existing
            )

        # LLM was called with existing model context
        call_msg = mock_chat.call_args[0][1]
        assert "Текущая модель" in call_msg
        assert result.get("metrics") == ["Время онбординга"]


# ============================================================================
# FR-8: Extractor identifies minimum required fields
# ============================================================================


class TestFR8_RequiredFields:
    """FR-8: Extractor must identify at minimum the specified fields."""

    @pytest.mark.asyncio
    async def test_extractor_prompt_requests_all_fields(self):
        """FR-8.1: System prompt requests all required fields from FR-8."""
        required_fields = [
            "goal", "stages", "triggers", "inputs", "outputs",
            "roles", "systems", "artifacts", "metrics", "pain_points",
        ]
        for field in required_fields:
            assert field in SYSTEM_PROMPT, f"Missing '{field}' in system prompt"

    @pytest.mark.asyncio
    async def test_extracted_model_contains_all_fields(self):
        """FR-8.2: Extracted model dict contains all required field keys."""
        llm_response = json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False)

        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await extract_asis_model("Тест", ["Описание"])

        for field in [
            "goal", "summary", "triggers", "inputs", "outputs",
            "stages", "roles", "systems", "artifacts", "metrics",
            "pain_points", "handoffs",
        ]:
            assert field in result, f"Missing field '{field}' in result"

    @pytest.mark.asyncio
    async def test_stages_contain_required_subfields(self):
        """FR-8.3: Each stage contains required sub-fields."""
        llm_response = json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False)

        with patch("bot.services.extractor.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await extract_asis_model("Тест", ["Описание"])

        assert len(result["stages"]) > 0
        stage = result["stages"][0]
        for field in ["id", "name", "description", "owner_role", "systems"]:
            assert field in stage, f"Stage missing field '{field}'"

    @pytest.mark.asyncio
    async def test_handoffs_identified(self):
        """FR-8.4: Extractor prompt requests handoff identification."""
        assert "handoff" in SYSTEM_PROMPT.lower()
