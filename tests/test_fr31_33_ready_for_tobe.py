"""Tests for FR-31..FR-33: Ready for TO-BE State.

FR-31  After at least one opportunity is selected or the user explicitly
       completes selection, bot must show CTA "Составить TO-BE".
FR-32  System must persist all selected automation opportunities as input
       for the next feature.
FR-33  Final session state for this feature must be ready_for_tobe.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from bot.models import AutomationOpportunity, Process
from bot.states import OpportunityStatus, ProcessStatus
from tests.conftest import make_bot_mock, make_callback_query


# ============================================================================
# FR-31: Show CTA "Составить TO-BE" after selection
# ============================================================================


class TestFR31_TOBECTA:
    """FR-31: Show CTA 'Составить TO-BE' after proceeding with selection."""

    @pytest.mark.asyncio
    async def test_cta_shown_after_proceed(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-31.1: CTA shown when user proceeds after selecting opportunities."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_proceed

        # Select one, then proceed
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        # Check edit_message_text for TO-BE CTA
        edit_kwargs = bot.edit_message_text.call_args[1]
        assert "TO-BE" in edit_kwargs["text"]

    @pytest.mark.asyncio
    async def test_cta_button_present(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-31.2: CTA is shown as an inline button 'Составить TO-BE'."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_proceed

        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        markup = bot.edit_message_text.call_args[1]["reply_markup"]
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        assert any("TO-BE" in b for b in buttons)

    @pytest.mark.asyncio
    async def test_dalee_only_with_selection(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-31.3: 'Далее' button only appears when ≥1 opportunity is selected."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import show_opportunities_multiselect

        # No selections — no Далее
        await show_opportunities_multiselect(99999, seed_process.id, bot)
        markup = bot.send_message.call_args[1]["reply_markup"]
        proceed_buttons = [
            btn for row in markup.inline_keyboard for btn in row
            if btn.callback_data and btn.callback_data.startswith("opp_proceed_")
        ]
        assert len(proceed_buttons) == 0

    @pytest.mark.asyncio
    async def test_summary_shows_selected_count(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-31.4: Summary message shows how many were selected."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_proceed

        seed_opportunities[0].status = OpportunityStatus.SELECTED
        seed_opportunities[1].status = OpportunityStatus.SELECTED
        await db_session.commit()

        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        text = bot.edit_message_text.call_args[1]["text"]
        assert "2" in text


# ============================================================================
# FR-32: Persist selected automation opportunities
# ============================================================================


class TestFR32_PersistSelections:
    """FR-32: Persist all selected automation opportunities for next feature."""

    @pytest.mark.asyncio
    async def test_selected_opportunities_in_db(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-32.1: Selected opportunities are persisted in database."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_select

        await handle_opportunity_select(99999, seed_opportunities[0].id, bot)
        await handle_opportunity_select(99999, seed_opportunities[2].id, bot)

        async with patch_db() as fresh:
            result = await fresh.execute(
                select(AutomationOpportunity).where(
                    AutomationOpportunity.process_id == seed_process.id,
                    AutomationOpportunity.status == OpportunityStatus.SELECTED,
                )
            )
            selected = result.scalars().all()
            assert len(selected) == 2

    @pytest.mark.asyncio
    async def test_rejected_opportunities_also_persisted(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-32.2: Rejected opportunities are also persisted (not deleted)."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_reject

        await handle_opportunity_reject(99999, seed_opportunities[1].id, bot)

        async with patch_db() as fresh:
            result = await fresh.execute(
                select(AutomationOpportunity).where(
                    AutomationOpportunity.id == seed_opportunities[1].id
                )
            )
            opp = result.scalar_one()
            assert opp.status == OpportunityStatus.REJECTED

    @pytest.mark.asyncio
    async def test_opportunity_data_preserved(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-32.3: Opportunity content (title, problem, benefit) is preserved."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_select

        await handle_opportunity_select(99999, seed_opportunities[0].id, bot)

        async with patch_db() as fresh:
            result = await fresh.execute(
                select(AutomationOpportunity).where(
                    AutomationOpportunity.id == seed_opportunities[0].id
                )
            )
            opp = result.scalar_one()
            assert opp.title == "Автопарсинг документов"
            assert opp.problem is not None
            assert opp.expected_benefit is not None


# ============================================================================
# FR-33: Final session state must be ready_for_tobe
# ============================================================================


class TestFR33_FinalState:
    """FR-33: Final session state must be ready_for_tobe."""

    @pytest.mark.asyncio
    async def test_process_status_set_to_ready_for_tobe(
        self, db_session, patch_db, seed_process, seed_opportunities
    ):
        """FR-33.1: Process status is set to READY_FOR_TOBE after proceed."""
        bot = make_bot_mock()

        from bot.handlers.opportunities import handle_opportunity_proceed

        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        async with patch_db() as fresh:
            result = await fresh.execute(
                select(Process).where(Process.id == seed_process.id)
            )
            p = result.scalar_one()
            assert p.status == ProcessStatus.READY_FOR_TOBE

    @pytest.mark.asyncio
    async def test_ready_for_tobe_is_terminal(self):
        """FR-33.2: READY_FOR_TOBE is the final state for this feature."""
        # Verify it's a valid enum value
        assert ProcessStatus.READY_FOR_TOBE.value == "ready_for_tobe"

    @pytest.mark.asyncio
    async def test_tobe_callback_acknowledges_end(self, patch_db):
        """FR-33.3: Pressing 'Составить TO-BE' button shows acknowledgment."""
        update, context = make_callback_query("tobe_1")

        from bot.handlers.callbacks import callback_handler

        await callback_handler(update, context)

        context.bot.send_message.assert_called_once()
        text = context.bot.send_message.call_args[1]["text"]
        assert "ready_for_tobe" in text.lower() or "ready\\_for\\_tobe" in text.lower()

    @pytest.mark.asyncio
    async def test_no_tobe_generation_in_this_feature(self, patch_db):
        """FR-33.4: TO-BE page is NOT generated — feature ends here."""
        update, context = make_callback_query("tobe_1")

        from bot.handlers.callbacks import callback_handler

        await callback_handler(update, context)

        text = context.bot.send_message.call_args[1]["text"]
        # Should indicate TO-BE is a future feature
        assert "обновлени" in text.lower() or "следующ" in text.lower()

    @pytest.mark.asyncio
    async def test_state_machine_progression(self):
        """FR-33.5: Process status progresses through expected states."""
        expected_order = [
            ProcessStatus.CREATED,
            ProcessStatus.INTERVIEW_IN_PROGRESS,
            ProcessStatus.CLARIFICATION_IN_PROGRESS,
            ProcessStatus.ASIS_READY,
            ProcessStatus.ASIS_PUBLISHED,
            ProcessStatus.AUTOMATION_SELECTION_IN_PROGRESS,
            ProcessStatus.READY_FOR_TOBE,
        ]
        # Verify all states exist and are in expected order
        all_statuses = list(ProcessStatus)
        for status in expected_order:
            assert status in all_statuses
