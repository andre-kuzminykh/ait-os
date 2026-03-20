"""Tests for FR-53..FR-55: Process list pagination and opportunities multiselect."""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.handlers.callbacks import callback_handler, save_chat_context
from bot.handlers.opportunities import (
    handle_opportunity_proceed,
    handle_opportunity_toggle,
    show_opportunities_multiselect,
)
from bot.handlers.start import PAGE_SIZE, show_process_list
from bot.models import (
    AutomationOpportunity,
    Company,
    InterviewSession,
    Process,
    Respondent,
)
from bot.states import OpportunityStatus, OpportunityType, ProcessStatus, SessionStatus
from tests.conftest import BotMock, make_callback_query

# ═══════════════════════════════════════════════════════════════════════
# FR-53: Process list pagination
# ═══════════════════════════════════════════════════════════════════════


class TestFR53_PageSize:
    """PAGE_SIZE constant is 10."""

    def test_page_size_is_10(self):
        assert PAGE_SIZE == 10


class TestFR53_PaginationUnderLimit:
    """When processes ≤ PAGE_SIZE, no arrows shown."""

    @pytest.mark.asyncio
    async def test_no_arrows_when_few_processes(self, db_session, patch_db):
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=77777, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        # Create 3 processes (< PAGE_SIZE)
        for i in range(3):
            p = Process(company_id=company.id, name=f"Proc {i}", status=ProcessStatus.CREATED)
            db_session.add(p)
            await db_session.flush()
            s = InterviewSession(
                process_id=p.id, respondent_id=respondent.id,
                state=SessionStatus.STARTED,
            )
            db_session.add(s)

        await db_session.commit()

        bot = BotMock()
        await show_process_list(99999, bot, 77777)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # Should have 3 process buttons + 1 "new process" button = 4 rows
        assert len(markup.inline_keyboard) == 4
        # No arrows — last row should be "Новый процесс"
        last_row = markup.inline_keyboard[-1]
        assert last_row[0].callback_data == "new_process"


class TestFR53_PaginationOverLimit:
    """When processes > PAGE_SIZE, arrows and page indicator shown."""

    @pytest.fixture()
    def _seed_many(self):
        """Marker — actual seeding in the test."""

    @pytest.mark.asyncio
    async def test_arrows_when_many_processes(self, db_session, patch_db):
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88888, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        # Create 15 processes (> PAGE_SIZE=10)
        for i in range(15):
            p = Process(company_id=company.id, name=f"Proc {i}", status=ProcessStatus.CREATED)
            db_session.add(p)
            await db_session.flush()
            s = InterviewSession(
                process_id=p.id, respondent_id=respondent.id,
                state=SessionStatus.STARTED,
            )
            db_session.add(s)

        await db_session.commit()

        bot = BotMock()
        await show_process_list(99999, bot, 88888, page=0)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # Page 0: 10 processes + nav row + new process = 12 rows
        assert len(markup.inline_keyboard) == 12

        # Nav row is second to last
        nav_row = markup.inline_keyboard[-2]
        # First page: page indicator + right arrow (no left arrow)
        assert any("1/2" in btn.text for btn in nav_row)
        assert any(btn.callback_data == "page_1" for btn in nav_row)
        # No left arrow on first page
        assert not any(btn.callback_data == "page_-1" for btn in nav_row)

    @pytest.mark.asyncio
    async def test_second_page_has_left_arrow(self, db_session, patch_db):
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88889, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(15):
            p = Process(company_id=company.id, name=f"Proc {i}", status=ProcessStatus.CREATED)
            db_session.add(p)
            await db_session.flush()
            s = InterviewSession(
                process_id=p.id, respondent_id=respondent.id,
                state=SessionStatus.STARTED,
            )
            db_session.add(s)

        await db_session.commit()

        bot = BotMock()
        await show_process_list(99999, bot, 88889, page=1)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # Page 1: 5 processes + nav row + new process = 7 rows
        assert len(markup.inline_keyboard) == 7

        # Nav row
        nav_row = markup.inline_keyboard[-2]
        # Has left arrow and page indicator, no right arrow (last page)
        assert any(btn.callback_data == "page_0" for btn in nav_row)
        assert any("2/2" in btn.text for btn in nav_row)

    @pytest.mark.asyncio
    async def test_exactly_10_no_arrows(self, db_session, patch_db):
        """Exactly PAGE_SIZE processes — no pagination needed."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88890, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(10):
            p = Process(company_id=company.id, name=f"Proc {i}", status=ProcessStatus.CREATED)
            db_session.add(p)
            await db_session.flush()
            s = InterviewSession(
                process_id=p.id, respondent_id=respondent.id,
                state=SessionStatus.STARTED,
            )
            db_session.add(s)

        await db_session.commit()

        bot = BotMock()
        await show_process_list(99999, bot, 88890)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # 10 processes + new process button = 11 rows (no nav)
        assert len(markup.inline_keyboard) == 11
        last_row = markup.inline_keyboard[-1]
        assert last_row[0].callback_data == "new_process"


class TestFR53_PageCallback:
    """Page navigation callback dispatches correctly."""

    @pytest.mark.asyncio
    async def test_page_callback_routes(self, db_session, patch_db):
        """page_N callback triggers show_process_list with correct page."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=77770, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(15):
            p = Process(company_id=company.id, name=f"Proc {i}", status=ProcessStatus.CREATED)
            db_session.add(p)
            await db_session.flush()
            s = InterviewSession(
                process_id=p.id, respondent_id=respondent.id,
                state=SessionStatus.STARTED,
            )
            db_session.add(s)

        await db_session.commit()

        # Save context with telegram_user_id
        await save_chat_context(99999, {"telegram_user_id": 77770})

        update, context = make_callback_query("page_1", chat_id=99999)
        update.callback_query.message.message_id = 500
        update.effective_user = MagicMock()
        update.effective_user.id = 77770

        await callback_handler(update, context)

        # Should have edited the message (not sent a new one)
        context.bot.edit_message_text.assert_called_once()
        edit_kwargs = context.bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == 500

    @pytest.mark.asyncio
    async def test_page_noop_does_nothing(self):
        """page_noop callback is a no-op."""
        update, context = make_callback_query("page_noop", chat_id=99999)
        update.effective_user = MagicMock()
        update.effective_user.id = 77770

        # Should not raise
        await callback_handler(update, context)
        context.bot.send_message.assert_not_called()
        context.bot.edit_message_text.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# FR-54: Opportunities multiselect toggle
# ═══════════════════════════════════════════════════════════════════════


class TestFR54_MultiselectDisplay:
    """Opportunities displayed as multiselect toggle buttons."""

    @pytest.mark.asyncio
    async def test_shows_all_opportunities_as_buttons(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        text = call_kwargs["text"]
        markup = call_kwargs["reply_markup"]

        # Text contains description header
        assert "Потенциал автоматизации" in text

        # Each opportunity is shown in text
        for opp in seed_opportunities:
            assert opp.title in text

        # Each opportunity has a toggle button
        toggle_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_toggle_")
        ]
        assert len(toggle_buttons) == len(seed_opportunities)

    @pytest.mark.asyncio
    async def test_all_initially_unchecked(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """All opportunities start as PROPOSED (unchecked ⬜)."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        toggle_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_toggle_")
        ]
        for btn in toggle_buttons:
            assert btn.text.startswith("⬜")

    @pytest.mark.asyncio
    async def test_no_dalee_when_none_selected(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """'Далее' button not shown when 0 selected."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        proceed_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_proceed_")
        ]
        assert len(proceed_buttons) == 0

    @pytest.mark.asyncio
    async def test_shows_problem_and_benefit(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Text includes problem and expected benefit."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        # Check at least one problem and benefit is shown
        assert "HR вручную вносит данные из паспорта" in text
        assert "Сокращение ошибок на 80%" in text

    @pytest.mark.asyncio
    async def test_shows_type_labels(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Type labels (AI, Integration, etc.) shown in text."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "🤖 AI" in text
        assert "🔗 Интеграция" in text
        assert "📊 Аналитика" in text

    @pytest.mark.asyncio
    async def test_no_opps_message(self, db_session, patch_db, seed_process):
        """When no opportunities found, shows appropriate message."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "Не удалось выявить" in text


class TestFR54_Toggle:
    """Toggle changes opportunity status and re-renders."""

    @pytest.mark.asyncio
    async def test_toggle_selects_opportunity(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Toggling a PROPOSED opp changes it to SELECTED."""
        opp = seed_opportunities[0]
        assert opp.status == OpportunityStatus.PROPOSED

        bot = BotMock()
        await handle_opportunity_toggle(99999, opp.id, bot, message_id=500)

        # After toggle, re-check from DB
        await db_session.refresh(opp)
        assert opp.status == OpportunityStatus.SELECTED

    @pytest.mark.asyncio
    async def test_toggle_deselects_opportunity(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Toggling a SELECTED opp changes it back to PROPOSED."""
        opp = seed_opportunities[0]
        opp.status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_toggle(99999, opp.id, bot, message_id=500)

        await db_session.refresh(opp)
        assert opp.status == OpportunityStatus.PROPOSED

    @pytest.mark.asyncio
    async def test_dalee_appears_after_selection(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """After selecting at least 1, 'Далее' button appears."""
        opp = seed_opportunities[0]
        bot = BotMock()

        # Toggle to select
        await handle_opportunity_toggle(99999, opp.id, bot, message_id=500)

        # The re-render should show Далее
        edit_kwargs = bot.edit_message_text.call_args[1]
        markup = edit_kwargs["reply_markup"]

        proceed_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_proceed_")
        ]
        assert len(proceed_buttons) == 1
        assert "Далее" in proceed_buttons[0].text

    @pytest.mark.asyncio
    async def test_dalee_shows_selected_count(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """'Далее' button shows count of selected items."""
        # Select two opportunities
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        seed_opportunities[1].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot, message_id=500)

        edit_kwargs = bot.edit_message_text.call_args[1]
        markup = edit_kwargs["reply_markup"]

        proceed_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_proceed_")
        ]
        assert len(proceed_buttons) == 1
        assert "2 выбрано" in proceed_buttons[0].text

    @pytest.mark.asyncio
    async def test_selected_shows_checkmark(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Selected opportunity button shows ✅ prefix."""
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        toggle_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_toggle_")
        ]

        # First button (selected) should have ✅
        selected_btn = [b for b in toggle_buttons if f"opp_toggle_{seed_opportunities[0].id}" in b.callback_data][0]
        assert selected_btn.text.startswith("✅")

        # Other buttons should have ⬜
        unselected_btn = [b for b in toggle_buttons if f"opp_toggle_{seed_opportunities[1].id}" in b.callback_data][0]
        assert unselected_btn.text.startswith("⬜")


class TestFR54_ToggleCallback:
    """opp_toggle callback dispatches correctly."""

    @pytest.mark.asyncio
    async def test_toggle_callback_routes(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        opp = seed_opportunities[0]
        update, context = make_callback_query(f"opp_toggle_{opp.id}", chat_id=99999)
        update.callback_query.message.message_id = 500

        await callback_handler(update, context)

        # Should have been toggled (edit_message_text called for re-render)
        context.bot.edit_message_text.assert_called()


# ═══════════════════════════════════════════════════════════════════════
# FR-55: Proceed after selection
# ═══════════════════════════════════════════════════════════════════════


class TestFR55_Proceed:
    """After 'Далее', unselected marked REJECTED, process → READY_FOR_TOBE."""

    @pytest.mark.asyncio
    async def test_proceed_marks_unselected_rejected(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Unselected opps become REJECTED after proceed."""
        # Select first, leave others as PROPOSED
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        await db_session.refresh(seed_opportunities[1])
        await db_session.refresh(seed_opportunities[2])
        assert seed_opportunities[1].status == OpportunityStatus.REJECTED
        assert seed_opportunities[2].status == OpportunityStatus.REJECTED

    @pytest.mark.asyncio
    async def test_proceed_keeps_selected(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Selected opps stay SELECTED after proceed."""
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        seed_opportunities[1].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        await db_session.refresh(seed_opportunities[0])
        await db_session.refresh(seed_opportunities[1])
        assert seed_opportunities[0].status == OpportunityStatus.SELECTED
        assert seed_opportunities[1].status == OpportunityStatus.SELECTED

    @pytest.mark.asyncio
    async def test_proceed_sets_ready_for_tobe(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Process status becomes READY_FOR_TOBE."""
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        await db_session.refresh(seed_process)
        assert seed_process.status == ProcessStatus.READY_FOR_TOBE

    @pytest.mark.asyncio
    async def test_proceed_shows_stub(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Proceed shows stub message with TO-BE button."""
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        edit_kwargs = bot.edit_message_text.call_args[1]
        text = edit_kwargs["text"]
        markup = edit_kwargs["reply_markup"]

        assert "Выбрано" in text
        assert "TO-BE" in text

        # Has TO-BE button
        tobe_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("tobe_")
        ]
        assert len(tobe_buttons) == 1

    @pytest.mark.asyncio
    async def test_proceed_shows_selected_titles(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Stub message lists titles of selected opportunities."""
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        seed_opportunities[2].status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await handle_opportunity_proceed(99999, seed_process.id, bot, message_id=500)

        text = bot.edit_message_text.call_args[1]["text"]
        assert seed_opportunities[0].title in text
        assert seed_opportunities[2].title in text


class TestFR55_ProceedCallback:
    """opp_proceed callback dispatches correctly."""

    @pytest.mark.asyncio
    async def test_proceed_callback_routes(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        seed_opportunities[0].status = OpportunityStatus.SELECTED
        await db_session.commit()

        update, context = make_callback_query(
            f"opp_proceed_{seed_process.id}", chat_id=99999,
        )
        update.callback_query.message.message_id = 500

        await callback_handler(update, context)

        # Should show stub (edit_message_text called)
        context.bot.edit_message_text.assert_called()
        text = context.bot.edit_message_text.call_args[1]["text"]
        assert "Выбрано" in text


class TestFR54_SelectAll:
    """Can select all opportunities."""

    @pytest.mark.asyncio
    async def test_select_all_then_proceed(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """All opportunities can be selected."""
        for opp in seed_opportunities:
            opp.status = OpportunityStatus.SELECTED
        await db_session.commit()

        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # All buttons checked
        toggle_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_toggle_")
        ]
        for btn in toggle_buttons:
            assert btn.text.startswith("✅")

        # Далее shows count = 3
        proceed_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_proceed_")
        ]
        assert "3 выбрано" in proceed_buttons[0].text
