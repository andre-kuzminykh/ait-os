"""Tests for FR-25..FR-30: Automation Opportunity Discovery.

FR-25  System must generate automation opportunities based on AS-IS model.
FR-26  Each opportunity must include title, stage, problem, description,
       expected benefit, and optional type label.
FR-27  Opportunities must be deduplicated.
FR-28  Opportunities must be understandable for business users.
FR-29  Bot must display opportunities one by one or in small batches
       with inline selection buttons.
FR-30  Bot must persist selection status for each opportunity.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from bot.models import AutomationOpportunity
from bot.services.opportunities import generate_opportunities, SYSTEM_PROMPT
from bot.states import OpportunityStatus
from tests.conftest import make_bot_mock, SAMPLE_ASIS_MODEL, SAMPLE_OPPORTUNITIES


# ============================================================================
# FR-25: Generate automation opportunities based on AS-IS model
# ============================================================================


class TestFR25_OpportunityGeneration:
    """FR-25: Generate automation opportunities from AS-IS model."""

    @pytest.mark.asyncio
    async def test_opportunities_generated_from_model(self):
        """FR-25.1: Opportunity generator returns a list from AS-IS model."""
        llm_response = json.dumps(
            {"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False
        )

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Онбординг", SAMPLE_ASIS_MODEL)

        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_opportunities_empty_on_llm_failure(self):
        """FR-25.2: Returns empty list on LLM parse failure."""
        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value="broken"):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        assert result == []

    @pytest.mark.asyncio
    async def test_opportunities_prompt_analyzes_pain_points(self):
        """FR-25.3: Prompt instructs analysis of pain points and bottlenecks."""
        for term in ["болевые точки", "узкие места", "ручные"]:
            assert term in SYSTEM_PROMPT.lower(), f"Missing '{term}' in prompt"


# ============================================================================
# FR-26: Each opportunity includes required fields
# ============================================================================


class TestFR26_OpportunityFields:
    """FR-26: Each opportunity must include required fields."""

    @pytest.mark.asyncio
    async def test_opportunity_has_title(self):
        """FR-26.1: Each opportunity has a title."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        for opp in result:
            assert "title" in opp
            assert len(opp["title"]) > 0

    @pytest.mark.asyncio
    async def test_opportunity_has_problem(self):
        """FR-26.2: Each opportunity describes the problem it addresses."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        for opp in result:
            assert "problem" in opp

    @pytest.mark.asyncio
    async def test_opportunity_has_expected_benefit(self):
        """FR-26.3: Each opportunity has an expected benefit."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        for opp in result:
            assert "expected_benefit" in opp

    @pytest.mark.asyncio
    async def test_opportunity_has_type_label(self):
        """FR-26.4: Each opportunity has a type label."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        valid_types = {"ai", "rule_based", "integration", "analytics", "monitoring"}
        for opp in result:
            assert "type" in opp
            assert opp["type"] in valid_types

    @pytest.mark.asyncio
    async def test_opportunity_has_stage_reference(self):
        """FR-26.5: Each opportunity references a stage or is process-level."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        for opp in result:
            assert "stage_id" in opp

    @pytest.mark.asyncio
    async def test_opportunity_has_description(self):
        """FR-26.6: Each opportunity has a description."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        for opp in result:
            assert "description" in opp


# ============================================================================
# FR-27: Opportunities must be deduplicated
# ============================================================================


class TestFR27_Deduplication:
    """FR-27: Opportunities must be deduplicated."""

    @pytest.mark.asyncio
    async def test_prompt_requires_deduplication(self):
        """FR-27.1: System prompt instructs not to duplicate opportunities."""
        assert "дублируй" in SYSTEM_PROMPT.lower() or "дубл" in SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_generated_opportunities_unique_titles(self):
        """FR-27.2: Generated opportunities have unique titles."""
        llm_response = json.dumps({"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False)

        with patch("bot.services.opportunities.chat", new_callable=AsyncMock, return_value=llm_response):
            result = await generate_opportunities("Тест", SAMPLE_ASIS_MODEL)

        titles = [o["title"] for o in result]
        assert len(titles) == len(set(titles))


# ============================================================================
# FR-28: Opportunities understandable for business users
# ============================================================================


class TestFR28_BusinessReadable:
    """FR-28: Opportunities must be understandable for business users."""

    @pytest.mark.asyncio
    async def test_prompt_requests_business_language(self):
        """FR-28.1: Prompt instructs to use business-user-understandable language."""
        assert "бизнес" in SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_prompt_limits_count(self):
        """FR-28.2: Prompt limits opportunities count (2-8) for digestibility."""
        assert "2" in SYSTEM_PROMPT and "8" in SYSTEM_PROMPT


# ============================================================================
# FR-29: Display opportunities with inline selection buttons
# ============================================================================


class TestFR29_InlineDisplay:
    """FR-29: Bot must display opportunities with inline toggle buttons (multiselect)."""

    @pytest.mark.asyncio
    async def test_opportunity_card_sent_to_user(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-29.1: Opportunities are sent as a multiselect message."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import send_next_opportunity

        await send_next_opportunity(99999, seed_process.id, bot)

        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[1]["text"]
        assert len(text) > 10

    @pytest.mark.asyncio
    async def test_card_has_toggle_buttons(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-29.2: Multiselect view has toggle buttons for each opportunity."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import send_next_opportunity

        await send_next_opportunity(99999, seed_process.id, bot)

        markup = bot.send_message.call_args[1]["reply_markup"]
        toggle_buttons = [
            btn for row in markup.inline_keyboard for btn in row
            if btn.callback_data and btn.callback_data.startswith("opp_toggle_")
        ]
        assert len(toggle_buttons) == len(seed_opportunities)

    @pytest.mark.asyncio
    async def test_toggle_buttons_show_unchecked(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-29.3: Initially all toggle buttons show ⬜ (unchecked)."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import send_next_opportunity

        await send_next_opportunity(99999, seed_process.id, bot)

        markup = bot.send_message.call_args[1]["reply_markup"]
        toggle_buttons = [
            btn for row in markup.inline_keyboard for btn in row
            if btn.callback_data and btn.callback_data.startswith("opp_toggle_")
        ]
        for btn in toggle_buttons:
            assert btn.text.startswith("⬜")

    @pytest.mark.asyncio
    async def test_card_shows_type_label(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-29.5: Card shows type label (AI, Integration, etc.)."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import send_next_opportunity

        await send_next_opportunity(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        # Should contain one of the type labels
        type_labels = ["AI", "Правила", "Интеграция", "Аналитика", "Мониторинг"]
        assert any(label in text for label in type_labels)

    @pytest.mark.asyncio
    async def test_detail_shows_full_description(
        self, db_session, patch_db, seed_opportunities
    ):
        """FR-29.6: 'Подробнее' shows full opportunity description."""
        opp = seed_opportunities[0]
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_detail

        await handle_opportunity_detail(99999, opp.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert opp.title in text


# ============================================================================
# FR-30: Persist selection status for each opportunity
# ============================================================================


class TestFR30_SelectionPersistence:
    """FR-30: Bot must persist selection status for each opportunity."""

    @pytest.mark.asyncio
    async def test_select_sets_status_selected(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-30.1: Selecting an opportunity sets status to SELECTED."""
        opp = seed_opportunities[0]
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_select

        await handle_opportunity_select(99999, opp.id, bot)

        await db_session.refresh(opp)
        assert opp.status == OpportunityStatus.SELECTED

    @pytest.mark.asyncio
    async def test_reject_sets_status_rejected(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-30.2: Rejecting an opportunity sets status to REJECTED."""
        opp = seed_opportunities[1]
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_reject

        await handle_opportunity_reject(99999, opp.id, bot)

        await db_session.refresh(opp)
        assert opp.status == OpportunityStatus.REJECTED

    @pytest.mark.asyncio
    async def test_status_persisted_in_db(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-30.3: Selection status is persisted in database after commit."""
        opp = seed_opportunities[0]
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_select

        await handle_opportunity_select(99999, opp.id, bot)

        # Use a fresh session from patch_db to verify persistence
        async with patch_db() as fresh_session:
            result = await fresh_session.execute(
                select(AutomationOpportunity).where(
                    AutomationOpportunity.id == opp.id
                )
            )
            db_opp = result.scalar_one()
            assert db_opp.status == OpportunityStatus.SELECTED

    @pytest.mark.asyncio
    async def test_multiple_opportunities_can_be_selected(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-30.4: Multiple opportunities can be selected independently."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_select, handle_opportunity_reject

        await handle_opportunity_select(99999, seed_opportunities[0].id, bot)
        await handle_opportunity_select(99999, seed_opportunities[2].id, bot)
        await handle_opportunity_reject(99999, seed_opportunities[1].id, bot)

        async with patch_db() as fresh:
            for opp_id, expected in [
                (seed_opportunities[0].id, OpportunityStatus.SELECTED),
                (seed_opportunities[1].id, OpportunityStatus.REJECTED),
                (seed_opportunities[2].id, OpportunityStatus.SELECTED),
            ]:
                result = await fresh.execute(
                    select(AutomationOpportunity).where(AutomationOpportunity.id == opp_id)
                )
                assert result.scalar_one().status == expected

    @pytest.mark.asyncio
    async def test_proposed_is_default_status(self, seed_opportunities):
        """FR-30.5: Default opportunity status is PROPOSED."""
        for opp in seed_opportunities:
            assert opp.status == OpportunityStatus.PROPOSED
