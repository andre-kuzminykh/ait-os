"""Tests for FR-18..FR-24: AS-IS Generation.

FR-18  System must generate AS-IS description in structured intermediate format.
FR-19  System must generate AS-IS narrative content for all supported sections.
FR-20  System must generate Mermaid code in a separate call from narrative.
FR-21  System must validate Mermaid syntax before publication.
FR-22  System must assemble narrative + Mermaid into branded HTML template.
FR-23  System must publish the resulting page and return a stable URL.
FR-24  Bot must send the page URL back to the user.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.generator import generate_narrative, SYSTEM_PROMPT as NARRATIVE_PROMPT
from bot.services.mermaid import (
    generate_mermaid,
    sanitize_mermaid,
    validate_mermaid,
)
from bot.services.publisher import publish_page
from tests.conftest import (
    make_bot_mock,
    SAMPLE_ASIS_MODEL,
    SAMPLE_MERMAID,
    SAMPLE_NARRATIVE,
    SAMPLE_OPPORTUNITIES,
)


# ============================================================================
# FR-18: Generate AS-IS in structured intermediate format
# ============================================================================


class TestFR18_IntermediateFormat:
    """FR-18: Generate AS-IS in structured intermediate format before rendering."""

    @pytest.mark.asyncio
    async def test_asis_model_stored_in_db(self, seed_asis_model):
        """FR-18.1: AS-IS model is stored as structured data in database."""
        assert seed_asis_model.goal is not None
        stages = json.loads(seed_asis_model.stages)
        assert isinstance(stages, list)
        assert len(stages) > 0

    @pytest.mark.asyncio
    async def test_asis_model_has_version(self, seed_asis_model):
        """FR-18.2: AS-IS model has a version number."""
        assert seed_asis_model.version >= 1

    @pytest.mark.asyncio
    async def test_asis_model_has_completeness_score(self, seed_asis_model):
        """FR-18.3: AS-IS model has a completeness score."""
        assert 0.0 <= seed_asis_model.completeness_score <= 1.0


# ============================================================================
# FR-19: Generate narrative content for all supported sections
# ============================================================================


class TestFR19_NarrativeGeneration:
    """FR-19: Generate narrative content for all supported HTML sections."""

    @pytest.mark.asyncio
    async def test_narrative_returns_all_sections(self):
        """FR-19.1: Narrative generator returns all HTML section keys."""
        llm_response = json.dumps(SAMPLE_NARRATIVE, ensure_ascii=False)

        with patch("bot.services.generator.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_narrative("Онбординг", SAMPLE_ASIS_MODEL)

        expected_keys = [
            "title", "goal", "summary", "triggers_html", "inputs_html",
            "outputs_html", "roles_html", "systems_html", "artifacts_html",
            "stages_html", "pain_points_html",
        ]
        for key in expected_keys:
            assert key in result, f"Missing section '{key}'"

    @pytest.mark.asyncio
    async def test_narrative_prompt_requests_html_format(self):
        """FR-19.2: Narrative prompt requests HTML-formatted sections."""
        assert "HTML" in NARRATIVE_PROMPT or "html" in NARRATIVE_PROMPT

    @pytest.mark.asyncio
    async def test_narrative_handles_invalid_json(self):
        """FR-19.3: Narrative generator returns fallback on invalid JSON."""
        with patch("bot.services.generator.chat", new_callable=AsyncMock, return_value="broken"):
            result = await generate_narrative("Тест", SAMPLE_ASIS_MODEL)

        assert "title" in result  # Fallback sets title
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_narrative_includes_automation_candidates(self):
        """FR-19.4: Narrative includes automation_candidates_html section."""
        llm_response = json.dumps(SAMPLE_NARRATIVE, ensure_ascii=False)

        with patch("bot.services.generator.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_narrative("Онбординг", SAMPLE_ASIS_MODEL)

        assert "automation_candidates_html" in result


# ============================================================================
# FR-20: Generate Mermaid code in a separate call
# ============================================================================


class TestFR20_SeparateMermaidCall:
    """FR-20: Mermaid generated in a separate LLM call from narrative."""

    @pytest.mark.asyncio
    async def test_mermaid_generator_exists_separately(self):
        """FR-20.1: Mermaid generator is a separate function from narrative."""
        from bot.services.mermaid import generate_mermaid as mermaid_fn
        from bot.services.generator import generate_narrative as narr_fn

        assert mermaid_fn is not narr_fn

    @pytest.mark.asyncio
    async def test_mermaid_returns_flowchart_code(self):
        """FR-20.2: Mermaid generator returns flowchart code."""
        with patch("bot.services.mermaid.chat", new_callable=AsyncMock, return_value=SAMPLE_MERMAID):
            result = await generate_mermaid("Онбординг", SAMPLE_ASIS_MODEL)

        assert "flowchart" in result.lower() or "graph" in result.lower()

    @pytest.mark.asyncio
    async def test_mermaid_returns_empty_on_failure(self):
        """FR-20.3: Mermaid returns empty string on repeated failure."""
        with patch("bot.services.mermaid.chat", new_callable=AsyncMock, return_value="invalid diagram"):
            result = await generate_mermaid("Тест", SAMPLE_ASIS_MODEL)

        assert result == ""


# ============================================================================
# FR-21: Validate Mermaid syntax before publication
# ============================================================================


class TestFR21_MermaidValidation:
    """FR-21: System must validate Mermaid syntax before publication."""

    def test_valid_flowchart_td(self):
        """FR-21.1: Valid flowchart TD code passes validation."""
        assert validate_mermaid("flowchart TD\n    A --> B") is True

    def test_valid_graph_lr(self):
        """FR-21.2: Valid graph LR code passes validation."""
        assert validate_mermaid("graph LR\n    A --> B") is True

    def test_empty_code_fails(self):
        """FR-21.3: Empty code fails validation."""
        assert validate_mermaid("") is False
        assert validate_mermaid("   ") is False

    def test_random_text_fails(self):
        """FR-21.4: Random text fails validation."""
        assert validate_mermaid("Это не диаграмма") is False

    def test_sanitize_removes_fences(self):
        """FR-21.5: Sanitizer removes markdown code fences."""
        code = "```mermaid\nflowchart TD\n    A --> B\n```"
        result = sanitize_mermaid(code)
        assert not result.startswith("```")
        assert "flowchart TD" in result

    @pytest.mark.asyncio
    async def test_mermaid_retries_on_validation_failure(self):
        """FR-21.6: Mermaid generator retries on first validation failure."""
        call_count = 0

        async def mock_chat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "bad diagram"
            return SAMPLE_MERMAID

        with patch("bot.services.mermaid.chat", side_effect=mock_chat):
            result = await generate_mermaid("Тест", SAMPLE_ASIS_MODEL)

        assert call_count == 2
        assert "flowchart" in result.lower()


# ============================================================================
# FR-22: Assemble narrative + Mermaid into branded HTML template
# ============================================================================


class TestFR22_HtmlAssembly:
    """FR-22: Assemble narrative + Mermaid into branded HTML template."""

    @pytest.mark.asyncio
    async def test_publish_creates_html_file(self, tmp_path):
        """FR-22.1: Publisher creates an HTML file on disk."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            url = await publish_page("test_token", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        assert (tmp_path / "test_token.html").exists()

    @pytest.mark.asyncio
    async def test_html_contains_narrative_sections(self, tmp_path):
        """FR-22.2: HTML contains all narrative sections."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            await publish_page("test_sections", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        html = (tmp_path / "test_sections.html").read_text(encoding="utf-8")
        assert "Онбординг" in html
        assert "Ввести нового сотрудника" in html

    @pytest.mark.asyncio
    async def test_html_contains_mermaid_code(self, tmp_path):
        """FR-22.3: HTML contains Mermaid diagram code."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            await publish_page("test_mermaid", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        html = (tmp_path / "test_mermaid.html").read_text(encoding="utf-8")
        assert "mermaid" in html
        assert "flowchart" in html

    @pytest.mark.asyncio
    async def test_html_has_brand(self, tmp_path):
        """FR-22.4: HTML contains Andre AI branding."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            await publish_page("test_brand", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        html = (tmp_path / "test_brand.html").read_text(encoding="utf-8")
        assert "Andre AI" in html

    @pytest.mark.asyncio
    async def test_html_is_responsive(self, tmp_path):
        """FR-22.5: HTML has responsive viewport meta tag."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            await publish_page("test_resp", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        html = (tmp_path / "test_resp.html").read_text(encoding="utf-8")
        assert "viewport" in html

    @pytest.mark.asyncio
    async def test_html_without_mermaid(self, tmp_path):
        """FR-22.6: HTML renders without Mermaid when code is empty."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            await publish_page("no_mermaid", SAMPLE_NARRATIVE, "")

        html = (tmp_path / "no_mermaid.html").read_text(encoding="utf-8")
        # Page should still exist and be valid
        assert "Andre AI" in html


# ============================================================================
# FR-23: Publish page and return a stable URL
# ============================================================================


class TestFR23_Publication:
    """FR-23: Publish the resulting page and return a stable URL."""

    @pytest.mark.asyncio
    async def test_publish_returns_url(self, tmp_path):
        """FR-23.1: Publisher returns a URL string."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            url = await publish_page("test_url", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        assert url is not None
        assert "test_url.html" in url

    @pytest.mark.asyncio
    async def test_url_contains_token_not_raw_id(self, tmp_path):
        """FR-23.2: URL uses opaque token, not raw database IDs."""
        with patch("bot.services.publisher.PAGES_DIR", tmp_path):
            url = await publish_page("abc123token", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        assert "abc123token" in url

    @pytest.mark.asyncio
    async def test_publish_failure_returns_none(self):
        """FR-23.3: On publish failure, returns None."""
        with patch("bot.services.publisher._env.get_template", side_effect=Exception("template error")):
            url = await publish_page("fail", SAMPLE_NARRATIVE, SAMPLE_MERMAID)

        assert url is None


# ============================================================================
# FR-24: Bot sends page URL back to user
# ============================================================================


class TestFR24_SendUrl:
    """FR-24: Bot must send the page URL back to the user."""

    @pytest.mark.asyncio
    async def test_trigger_generation_sends_url(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path
    ):
        """FR-24.1: After generation, bot sends URL to user."""
        bot = make_bot_mock()

        with (
            patch(
                "bot.services.generator.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_NARRATIVE, ensure_ascii=False),
            ),
            patch(
                "bot.services.mermaid.chat",
                new_callable=AsyncMock,
                return_value=SAMPLE_MERMAID,
            ),
            patch("bot.services.publisher.PAGES_DIR", tmp_path),
            patch(
                "bot.services.opportunities.chat",
                new_callable=AsyncMock,
                return_value=json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False),
            ),
        ):
            from bot.handlers.clarification import trigger_asis_generation

            await trigger_asis_generation(99999, seed_process.id, bot)

        # Check that at least one message contains a URL
        all_texts = [
            call[1].get("text", "") for call in bot.send_message.call_args_list
        ]
        # Also check edit_message_text calls (progress messages)
        for call in bot.edit_message_text.call_args_list:
            all_texts.append(call[1].get("text", ""))
        url_sent = any("http" in t for t in all_texts)
        assert url_sent, f"No URL found in messages: {all_texts}"

    @pytest.mark.asyncio
    async def test_trigger_generation_sends_open_button(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path
    ):
        """FR-24.2: Bot sends 'Открыть AS-IS' button with URL."""
        bot = make_bot_mock()

        with (
            patch(
                "bot.services.generator.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_NARRATIVE, ensure_ascii=False),
            ),
            patch(
                "bot.services.mermaid.chat",
                new_callable=AsyncMock,
                return_value=SAMPLE_MERMAID,
            ),
            patch("bot.services.publisher.PAGES_DIR", tmp_path),
            patch(
                "bot.services.opportunities.chat",
                new_callable=AsyncMock,
                return_value=json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False),
            ),
        ):
            from bot.handlers.clarification import trigger_asis_generation

            await trigger_asis_generation(99999, seed_process.id, bot)

        # The final message should contain the URL (as text or button).
        # For https URLs, an inline button is used. For http/localhost, the URL
        # is embedded in the message text. Either way, verify AS-IS link exists.
        all_calls = list(bot.send_message.call_args_list) + list(bot.edit_message_text.call_args_list)
        found = False
        for call in all_calls:
            kwargs = call[1]
            text = kwargs.get("text", "")
            markup = kwargs.get("reply_markup")
            # Check inline button
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.text for row in markup.inline_keyboard for btn in row
                ]
                if any("AS-IS" in b for b in buttons):
                    found = True
                    break
            # Check text contains URL
            if ".html" in text and "AS-IS" in text:
                found = True
                break
        assert found, "No AS-IS link found in buttons or text"
