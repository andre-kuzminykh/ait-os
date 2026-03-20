"""Tests for FR-53..FR-55: Process list pagination and opportunities multiselect."""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.handlers.callbacks import callback_handler, save_chat_context
from bot.handlers.opportunities import (
    build_opportunities_html,
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
    PublishedPage,
    Respondent,
)
from bot.states import OpportunityStatus, OpportunityType, ProcessStatus, SessionStatus
from tests.conftest import BotMock, make_callback_query

# ═══════════════════════════════════════════════════════════════════════
# FR-53: Process list pagination
# ═══════════════════════════════════════════════════════════════════════


class TestFR53_PageSize:
    """PAGE_SIZE constant is 5."""

    def test_page_size_is_5(self):
        assert PAGE_SIZE == 5


class TestFR53_PaginationUnderLimit:
    """When processes ≤ PAGE_SIZE, no nav row shown."""

    @pytest.mark.asyncio
    async def test_no_nav_when_few_processes(self, db_session, patch_db):
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=77777, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        # Create 3 processes (< PAGE_SIZE=5)
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

        # 3 processes + "Новый процесс" = 4 rows, no nav
        assert len(markup.inline_keyboard) == 4
        last_row = markup.inline_keyboard[-1]
        assert last_row[0].callback_data == "new_process"


class TestFR53_PaginationOverLimit:
    """When processes > PAGE_SIZE, nav row with 3 buttons shown."""

    @pytest.mark.asyncio
    async def test_nav_row_first_page(self, db_session, patch_db):
        """First page: inactive left (·), page indicator, active right."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88888, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        # Create 12 processes (> PAGE_SIZE=5, 3 pages)
        for i in range(12):
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

        # Page 0: 5 processes + nav row + new process = 7 rows
        assert len(markup.inline_keyboard) == 7

        # Nav row is second to last (above "Новый процесс")
        nav_row = markup.inline_keyboard[-2]
        assert len(nav_row) == 3  # always 3 buttons

        # Left is inactive (·, noop)
        assert nav_row[0].text == "·"
        assert nav_row[0].callback_data == "page_noop"
        # Center shows 1/3
        assert "1/3" in nav_row[1].text
        # Right is active
        assert nav_row[2].text == "➡️"
        assert nav_row[2].callback_data == "page_1"

    @pytest.mark.asyncio
    async def test_nav_row_last_page(self, db_session, patch_db):
        """Last page: active left, page indicator, inactive right (·)."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88889, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(12):
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
        await show_process_list(99999, bot, 88889, page=2)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        # Page 2: 2 processes + nav row + new process = 4 rows
        assert len(markup.inline_keyboard) == 4

        nav_row = markup.inline_keyboard[-2]
        assert len(nav_row) == 3

        # Left is active
        assert nav_row[0].text == "⬅️"
        assert nav_row[0].callback_data == "page_1"
        # Center shows 3/3
        assert "3/3" in nav_row[1].text
        # Right is inactive
        assert nav_row[2].text == "·"
        assert nav_row[2].callback_data == "page_noop"

    @pytest.mark.asyncio
    async def test_nav_row_middle_page(self, db_session, patch_db):
        """Middle page: both arrows active."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88891, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(12):
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
        await show_process_list(99999, bot, 88891, page=1)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]

        nav_row = markup.inline_keyboard[-2]
        assert len(nav_row) == 3
        assert nav_row[0].callback_data == "page_0"
        assert "2/3" in nav_row[1].text
        assert nav_row[2].callback_data == "page_2"

    @pytest.mark.asyncio
    async def test_exactly_5_no_nav(self, db_session, patch_db):
        """Exactly PAGE_SIZE processes — no nav row."""
        company = Company(name="Co")
        db_session.add(company)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=88890, display_name="U")
        db_session.add(respondent)
        await db_session.flush()

        for i in range(5):
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

        # 5 processes + new process button = 6 rows (no nav)
        assert len(markup.inline_keyboard) == 6
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
    async def test_shows_benefit(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Text includes expected benefit (without 'Эффект:' prefix)."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "Сокращение ошибок на 80%" in text
        # No "Эффект:" prefix
        assert "Эффект:" not in text

    @pytest.mark.asyncio
    async def test_shows_type_emoji(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Type emojis shown in text next to title."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "🤖" in text
        assert "🔗" in text
        assert "📊" in text

    @pytest.mark.asyncio
    async def test_no_opps_message(self, db_session, patch_db, seed_process):
        """When no opportunities found, shows appropriate message."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "Не удалось выявить" in text


class TestFR54_Spacing:
    """Message has blank lines between opportunity items for readability."""

    @pytest.mark.asyncio
    async def test_blank_lines_between_items(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """Each opportunity item is separated by a blank line."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        # Between items there should be double newlines (blank line)
        # e.g. "...benefit_\n\n2. Title..."
        assert "\n\n2." in text
        assert "\n\n3." in text


class TestFR54_MaxTen:
    """Display at most 10 opportunities."""

    @pytest.mark.asyncio
    async def test_max_10_opportunities_shown(
        self, db_session, patch_db, seed_process,
    ):
        """When >10 opportunities, only first 10 displayed."""
        # Create 12 opportunities
        for i in range(12):
            o = AutomationOpportunity(
                process_id=seed_process.id,
                title=f"Opp {i+1}",
                opp_type=OpportunityType.AI,
                expected_benefit=f"Benefit {i+1}",
                status=OpportunityStatus.PROPOSED,
            )
            db_session.add(o)
        await db_session.commit()

        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        text = call_kwargs["text"]
        markup = call_kwargs["reply_markup"]

        # Text should show 10. but not 11.
        assert "10." in text
        assert "11." not in text

        # Toggle buttons should be exactly 10
        toggle_buttons = [
            row[0] for row in markup.inline_keyboard
            if row[0].callback_data and row[0].callback_data.startswith("opp_toggle_")
        ]
        assert len(toggle_buttons) == 10


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


# ═══════════════════════════════════════════════════════════════════════
# FR-56: AS-IS link shown inline with opportunities
# ═══════════════════════════════════════════════════════════════════════


class TestFR56_AsisUrlInMultiselect:
    """asis_url shown as hyperlink at bottom, persists on toggle."""

    @pytest.mark.asyncio
    async def test_asis_url_as_hyperlink_at_bottom(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        bot = BotMock()
        await show_opportunities_multiselect(
            99999, seed_process.id, bot, asis_url="http://localhost:9090/pages/abc.html",
        )

        text = bot.send_message.call_args[1]["text"]
        assert "[📄 Открыть AS-IS](http://localhost:9090/pages/abc.html)" in text
        assert text.rstrip().endswith(")")

    @pytest.mark.asyncio
    async def test_no_url_when_no_published_page(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """No link when no asis_url and no published page in DB."""
        bot = BotMock()
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "Открыть AS-IS" not in text

    @pytest.mark.asyncio
    async def test_asis_url_fetched_from_db(
        self, db_session, patch_db, seed_process, seed_opportunities,
    ):
        """When asis_url not passed, fetch from PublishedPage in DB."""
        page = PublishedPage(
            process_id=seed_process.id,
            html_url="http://localhost:9090/pages/xyz.html",
        )
        db_session.add(page)
        await db_session.commit()

        bot = BotMock()
        # No asis_url passed — should auto-fetch from DB
        await show_opportunities_multiselect(99999, seed_process.id, bot)

        text = bot.send_message.call_args[1]["text"]
        assert "[📄 Открыть AS-IS](http://localhost:9090/pages/xyz.html)" in text


# ═══════════════════════════════════════════════════════════════════════
# FR-56b: HTML opportunities match TG format
# ═══════════════════════════════════════════════════════════════════════


class TestFR56b_HtmlOpportunitiesFormat:
    """build_opportunities_html produces compact HTML (titles only)."""

    def test_basic_html(self):
        opps = [
            {"title": "Авто-ответы", "type": "ai", "expected_benefit": "Сокращение на 80%"},
            {"title": "Интеграция Jira", "type": "integration", "expected_benefit": ""},
        ]
        html = build_opportunities_html(opps)
        assert "<ul>" in html
        assert "Авто-ответы 🤖" in html
        assert "Интеграция Jira 🔗" in html
        # HTML should NOT contain benefits — only titles
        assert "Сокращение на 80%" not in html
        assert "<em>" not in html

    def test_empty_list(self):
        assert build_opportunities_html([]) == ""

    def test_unknown_type(self):
        opps = [{"title": "Что-то", "type": "unknown", "expected_benefit": "Эффект"}]
        html = build_opportunities_html(opps)
        assert "Что-то" in html
        # Benefits not in HTML
        assert "Эффект" not in html


# ═══════════════════════════════════════════════════════════════════════
# FR-57: Mermaid sanitization
# ═══════════════════════════════════════════════════════════════════════


class TestFR57_MermaidSanitize:
    """Mermaid code is sanitized to prevent render errors."""

    def test_removes_quotes_from_labels(self):
        from bot.services.mermaid import sanitize_mermaid

        code = 'flowchart TD\n    A["Текст"] --> B["Другой"]'
        result = sanitize_mermaid(code)
        assert '["' not in result
        assert 'A[Текст]' in result

    def test_removes_special_chars(self):
        from bot.services.mermaid import sanitize_mermaid

        code = "flowchart TD\n    A[Текст & другой] --> B[#тест]"
        result = sanitize_mermaid(code)
        assert "&" not in result
        assert "#" not in result

    def test_removes_parentheses_in_labels(self):
        from bot.services.mermaid import sanitize_mermaid

        code = "flowchart TD\n    A[Получение запроса (клиент)] --> B[Ответ]"
        result = sanitize_mermaid(code)
        assert "(" not in result.split("-->")[0]

    def test_strips_markdown_fences(self):
        from bot.services.mermaid import sanitize_mermaid

        code = "```mermaid\nflowchart TD\n    A[Текст] --> B[Текст]\n```"
        result = sanitize_mermaid(code)
        assert not result.startswith("```")
        assert result.startswith("flowchart")


# ═══════════════════════════════════════════════════════════════════════
# FR-58: WeasyPrint optional
# ═══════════════════════════════════════════════════════════════════════


class TestFR58_WeasyPrintOptional:
    """WeasyPrint missing does not crash the app."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_available(self):
        from unittest.mock import patch
        with patch("bot.services.pdf_converter._WEASYPRINT_AVAILABLE", False):
            from bot.services.pdf_converter import convert_html_to_pdf
            result = await convert_html_to_pdf("nonexistent_token")
            assert result is None
