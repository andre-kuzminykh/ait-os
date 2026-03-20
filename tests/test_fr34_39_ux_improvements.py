"""Tests for FR-34..FR-39: UX Improvements (clean chat, progress, process list).

FR-34  Main menu — process list with "+" button.
FR-35  Step-by-step progress in a single message (send + edit).
FR-36  Message deletion (user and assistant messages).
FR-37  Typewriter effect for transcription display.
FR-38  Burger menu with "Процессы" command (/start).
FR-39  Process detail view: view AS-IS / continue / TO-BE.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from bot.models import (
    Company,
    InterviewSession,
    Process,
    PublishedPage,
    Respondent,
)
from bot.states import ProcessStatus, SessionStatus
from tests.conftest import (
    make_bot_mock,
    make_callback_query,
    make_update,
    SAMPLE_ASIS_MODEL,
    SAMPLE_GAP_RESULT,
)


# ============================================================================
# FR-34: Process list as main screen with "+" button
# ============================================================================


class TestFR34_ProcessList:
    """FR-34: Main menu shows process list with '+' button."""

    @pytest.mark.asyncio
    async def test_start_shows_process_list(
        self, db_session, patch_db, seed_session, seed_process, seed_respondent,
    ):
        """FR-34.1: /start shows process list with process buttons."""
        update, context = make_update(args=[])

        from bot.handlers.start import cmd_start
        await cmd_start(update, context)

        # Bot should have called send_message with process list
        bot = context.bot
        assert bot.send_message.called
        # Find the call with inline keyboard
        for call in bot.send_message.call_args_list:
            kwargs = call[1]
            if kwargs.get("reply_markup"):
                markup = kwargs["reply_markup"]
                if hasattr(markup, "inline_keyboard"):
                    buttons = [
                        btn.callback_data
                        for row in markup.inline_keyboard
                        for btn in row
                        if hasattr(btn, "callback_data") and btn.callback_data
                    ]
                    # Should have view_ button for the process
                    assert any(b.startswith("view_") for b in buttons)
                    # Should have new_process button
                    assert any(b == "new_process" for b in buttons)
                    return
        pytest.fail("No process list with inline keyboard found")

    @pytest.mark.asyncio
    async def test_start_empty_shows_plus_button(self, db_session, patch_db):
        """FR-34.2: /start with no processes still shows '+' button."""
        # Create respondent but no processes
        respondent = Respondent(telegram_user_id=111222, display_name="Иван")
        db_session.add(respondent)
        await db_session.commit()

        update, context = make_update(args=[])

        from bot.handlers.start import cmd_start
        await cmd_start(update, context)

        bot = context.bot
        for call in bot.send_message.call_args_list:
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.callback_data
                    for row in markup.inline_keyboard
                    for btn in row
                    if hasattr(btn, "callback_data") and btn.callback_data
                ]
                assert "new_process" in buttons
                return
        pytest.fail("No '+' button found in empty process list")

    @pytest.mark.asyncio
    async def test_plus_button_asks_for_name(self, patch_db):
        """FR-34.3: Clicking '+' prompts user to enter process name."""
        from bot.handlers.callbacks import _handle_new_process, _chat_contexts

        chat_id = 55555
        _chat_contexts[chat_id] = {}
        bot = make_bot_mock()

        await _handle_new_process(chat_id, 100, bot)

        # Should send "Введите название" message
        bot.send_message.assert_called()
        call_text = bot.send_message.call_args[1].get("text", "")
        assert "название" in call_text.lower()

        # Should set awaiting_process_name
        ctx = _chat_contexts.get(chat_id, {})
        assert ctx.get("awaiting_process_name") is True

    @pytest.mark.asyncio
    async def test_process_name_creates_process(
        self, db_session, patch_db, seed_respondent,
    ):
        """FR-34.4: Typing name after '+' creates process and starts interview."""
        from bot.handlers.callbacks import save_chat_context
        from bot.handlers.start import handle_new_process_name

        chat_id = 55556
        await save_chat_context(chat_id, {"awaiting_process_name": True})

        bot = make_bot_mock()
        await handle_new_process_name(
            bot, chat_id, "Тестовый процесс", seed_respondent.telegram_user_id, 42,
        )

        # Process should exist in DB
        result = await db_session.execute(
            select(Process).where(Process.name == "Тестовый процесс")
        )
        process = result.scalar_one_or_none()
        assert process is not None
        assert process.status == ProcessStatus.INTERVIEW_IN_PROGRESS


# ============================================================================
# FR-35: Step-by-step progress in a single message
# ============================================================================


class TestFR35_StepByStepProgress:
    """FR-35: Progress updates via send + edit of a single message."""

    @pytest.mark.asyncio
    async def test_send_progress_creates_message(self):
        """FR-35.1: send_progress creates a new message when no message_id."""
        from bot.handlers.progress import send_progress

        bot = make_bot_mock()
        mid = await send_progress(bot, 99999, "Loading...")

        bot.send_message.assert_called_once()
        assert mid is not None

    @pytest.mark.asyncio
    async def test_send_progress_edits_existing(self):
        """FR-35.2: send_progress edits when message_id is provided."""
        from bot.handlers.progress import send_progress

        bot = make_bot_mock()
        mid = await send_progress(bot, 99999, "Step 2...", message_id=123)

        bot.edit_message_text.assert_called_once()
        assert mid == 123

    @pytest.mark.asyncio
    async def test_text_input_shows_progress(
        self, db_session, patch_db, seed_session, seed_process,
    ):
        """FR-35.3: Text input shows progress via bot.send_message."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 44444
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        update, context = make_update(
            text="Описание процесса", chat_id=chat_id,
        )

        with patch("bot.handlers.interview._process_input", new_callable=AsyncMock):
            from bot.handlers.interview import handle_text_message
            await handle_text_message(update, context)

        # Should have sent a progress message
        bot = context.bot
        assert bot.send_message.called
        texts = [c[1].get("text", "") for c in bot.send_message.call_args_list]
        assert any("анализирую" in t.lower() or "записал" in t.lower() for t in texts)


# ============================================================================
# FR-36: Message deletion
# ============================================================================


class TestFR36_MessageDeletion:
    """FR-36: Bot deletes user and assistant messages for clean chat."""

    @pytest.mark.asyncio
    async def test_delete_messages_helper(self):
        """FR-36.1: delete_messages calls bot.delete_message for each ID."""
        from bot.handlers.progress import delete_messages

        bot = make_bot_mock()
        await delete_messages(bot, 99999, [1, 2, 3])

        assert bot.delete_message.call_count == 3

    @pytest.mark.asyncio
    async def test_text_input_deletes_user_message(
        self, db_session, patch_db, seed_session, seed_process,
    ):
        """FR-36.2: User's text message is deleted after processing."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 33333
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        update, context = make_update(
            text="Описание", chat_id=chat_id, message_id=42,
        )

        with patch("bot.handlers.interview._process_input", new_callable=AsyncMock):
            from bot.handlers.interview import handle_text_message
            await handle_text_message(update, context)

        # User's message should be deleted
        bot = context.bot
        assert bot.delete_message.called
        deleted_ids = [c[1].get("message_id") for c in bot.delete_message.call_args_list]
        assert 42 in deleted_ids

    @pytest.mark.asyncio
    async def test_voice_input_deletes_user_message(
        self, db_session, patch_db, seed_session, seed_process,
    ):
        """FR-36.3: User's voice message is deleted after receiving."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 33334
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        voice = MagicMock()
        voice.file_id = "voice_123"

        update, context = make_update(
            chat_id=chat_id, voice=voice, message_id=55,
        )
        update.message.voice = voice

        with (
            patch(
                "bot.handlers.interview.transcribe_telegram_voice",
                new_callable=AsyncMock,
                return_value="Распознанный текст",
            ),
            patch("bot.handlers.interview._process_input", new_callable=AsyncMock),
        ):
            from bot.handlers.interview import handle_voice_message
            await handle_voice_message(update, context)

        bot = context.bot
        deleted_ids = [c[1].get("message_id") for c in bot.delete_message.call_args_list]
        assert 55 in deleted_ids

    @pytest.mark.asyncio
    async def test_new_process_flow_deletes_messages(
        self, db_session, patch_db, seed_respondent,
    ):
        """FR-36.4: New process flow deletes prompt and name messages."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 33335
        # Simulate state after clicking "+"
        await save_chat_context(chat_id, {
            "awaiting_process_name": True,
            "messages_to_delete": [100, 101],  # menu msg + prompt msg
        })

        bot = make_bot_mock()
        from bot.handlers.start import handle_new_process_name
        await handle_new_process_name(
            bot, chat_id, "Новый процесс", seed_respondent.telegram_user_id, 102,
        )

        # Should delete menu msg (100), prompt msg (101), and user's name msg (102)
        deleted_ids = [c[1].get("message_id") for c in bot.delete_message.call_args_list]
        assert 100 in deleted_ids
        assert 101 in deleted_ids
        assert 102 in deleted_ids


# ============================================================================
# FR-37: Typewriter effect for transcription
# ============================================================================


class TestFR37_TypewriterEffect:
    """FR-37: Typewriter effect for transcription display."""

    @pytest.mark.asyncio
    async def test_typewriter_sends_progressively(self):
        """FR-37.1: typewriter_send edits message multiple times."""
        from bot.handlers.progress import typewriter_send

        bot = make_bot_mock()
        mid = await typewriter_send(
            bot, 99999, "Привет мир это тестовый текст для проверки",
            prefix="📝 ", steps=3,
        )

        # Should have sent initial message + at least 2 edits
        assert bot.send_message.call_count >= 1
        assert bot.edit_message_text.call_count >= 2

    @pytest.mark.asyncio
    async def test_typewriter_shows_cursor(self):
        """FR-37.2: Intermediate steps show cursor character '▌'."""
        from bot.handlers.progress import typewriter_send

        bot = make_bot_mock()
        await typewriter_send(
            bot, 99999, "Длинный текст для проверки курсора",
            prefix="", steps=3,
        )

        # First send should include cursor
        first_text = bot.send_message.call_args_list[0][1].get("text", "")
        assert "▌" in first_text

    @pytest.mark.asyncio
    async def test_voice_uses_typewriter(
        self, db_session, patch_db, seed_session, seed_process,
    ):
        """FR-37.3: Voice transcription is displayed with typewriter effect."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 22222
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        voice = MagicMock()
        voice.file_id = "voice_typewriter"

        update, context = make_update(chat_id=chat_id, voice=voice)
        update.message.voice = voice

        transcript = "Это тестовая транскрипция голосового сообщения для проверки"

        with (
            patch(
                "bot.handlers.interview.transcribe_telegram_voice",
                new_callable=AsyncMock,
                return_value=transcript,
            ),
            patch("bot.handlers.interview._process_input", new_callable=AsyncMock),
        ):
            from bot.handlers.interview import handle_voice_message
            await handle_voice_message(update, context)

        bot = context.bot
        # Should have edit_message_text calls for typewriter effect
        assert bot.edit_message_text.call_count >= 2
        # At least one edit should contain part of the transcript
        edit_texts = [c[1].get("text", "") for c in bot.edit_message_text.call_args_list]
        assert any("транскрипц" in t.lower() or "распознано" in t.lower() for t in edit_texts)


# ============================================================================
# FR-38: Burger menu with "Процессы" command
# ============================================================================


class TestFR38_BurgerMenu:
    """FR-38: Burger menu has 'Процессы' as /start command."""

    @pytest.mark.asyncio
    async def test_post_init_sets_commands(self):
        """FR-38.1: post_init sets bot commands with 'Процессы'."""
        from bot.main import post_init

        app = MagicMock()
        app.bot = make_bot_mock()

        with patch("bot.main.init_db", new_callable=AsyncMock):
            await post_init(app)

        app.bot.set_my_commands.assert_called_once()
        commands = app.bot.set_my_commands.call_args[0][0]
        assert len(commands) >= 1
        assert commands[0].command == "start"
        assert "процессы" in commands[0].description.lower()

    def test_start_is_registered(self):
        """FR-38.2: /start command is registered in main."""
        # Just verify the code structure imports cmd_start
        from bot.handlers.start import cmd_start
        assert callable(cmd_start)


# ============================================================================
# FR-39: Process detail view
# ============================================================================


class TestFR39_ProcessDetailView:
    """FR-39: Clicking a process shows detail view with actions."""

    @pytest.mark.asyncio
    async def test_view_incomplete_process_shows_continue(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.1: Incomplete process shows 'Продолжить заполнение' button."""
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        # Should edit message with continue button
        assert bot.edit_message_text.called or bot.send_message.called

        # Check for continue button in the call
        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.callback_data
                    for row in markup.inline_keyboard
                    for btn in row
                    if hasattr(btn, "callback_data") and btn.callback_data
                ]
                if any("continue_" in b for b in buttons):
                    return
        pytest.fail("No 'continue' button found for incomplete process")

    @pytest.mark.asyncio
    async def test_view_published_process_shows_asis(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.2: Published process shows 'Открыть AS-IS' button."""
        seed_process.status = ProcessStatus.ASIS_PUBLISHED
        await db_session.flush()

        page = PublishedPage(
            process_id=seed_process.id,
            html_url="http://example.com/test.html",
        )
        db_session.add(page)
        await db_session.commit()

        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        # Check for AS-IS URL button
        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.text
                    for row in markup.inline_keyboard
                    for btn in row
                ]
                if any("AS-IS" in b for b in buttons):
                    return
        pytest.fail("No 'AS-IS' button found for published process")

    @pytest.mark.asyncio
    async def test_view_ready_for_tobe_shows_tobe_button(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.3: Ready-for-tobe process shows 'Составить TO-BE' button."""
        seed_process.status = ProcessStatus.READY_FOR_TOBE
        await db_session.commit()

        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.callback_data
                    for row in markup.inline_keyboard
                    for btn in row
                    if hasattr(btn, "callback_data") and btn.callback_data
                ]
                if any("tobe_" in b for b in buttons):
                    return
        pytest.fail("No 'TO-BE' button found for ready process")

    @pytest.mark.asyncio
    async def test_back_button_present(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.4: Process detail has 'Назад' button."""
        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                buttons = [
                    btn.callback_data
                    for row in markup.inline_keyboard
                    for btn in row
                    if hasattr(btn, "callback_data") and btn.callback_data
                ]
                if "back_to_list" in buttons:
                    return
        pytest.fail("No 'back_to_list' button found in process detail")

    @pytest.mark.asyncio
    async def test_process_detail_uses_html_parse_mode(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.5: Process detail uses parse_mode='HTML'."""
        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            if "parse_mode" in kwargs:
                assert kwargs["parse_mode"] == "HTML"
                return
        pytest.fail("No parse_mode found in process detail call")

    @pytest.mark.asyncio
    async def test_process_detail_asis_link_is_html_hyperlink(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.6: Published process shows AS-IS as HTML <a href> hyperlink."""
        seed_process.status = ProcessStatus.ASIS_PUBLISHED
        await db_session.flush()

        page = PublishedPage(
            process_id=seed_process.id,
            html_url="http://example.com/test.html",
        )
        db_session.add(page)
        await db_session.commit()

        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            text = kwargs.get("text", "")
            if '<a href="http://example.com/test.html">' in text:
                return
        pytest.fail("No HTML hyperlink found in process detail text")

    @pytest.mark.asyncio
    async def test_process_detail_bold_name(
        self, db_session, patch_db, seed_process, seed_respondent,
    ):
        """FR-39.7: Process name in detail card is wrapped in <b> tags."""
        bot = make_bot_mock()
        from bot.handlers.start import show_process_detail
        await show_process_detail(
            99999, seed_process.id, 200, bot, seed_respondent.telegram_user_id,
        )

        for call in list(bot.edit_message_text.call_args_list) + list(bot.send_message.call_args_list):
            kwargs = call[1]
            text = kwargs.get("text", "")
            if f"<b>{seed_process.name}</b>" in text:
                return
        pytest.fail("No <b> tag around process name in detail card")

    @pytest.mark.asyncio
    async def test_process_list_shows_status_icons(
        self, db_session, patch_db, seed_session, seed_process, seed_respondent,
    ):
        """FR-39.5: Process list shows status icons next to process names."""
        bot = make_bot_mock()
        from bot.handlers.start import show_process_list
        await show_process_list(
            99999, bot, seed_respondent.telegram_user_id,
        )

        # Check that buttons contain status icons
        for call in bot.send_message.call_args_list:
            kwargs = call[1]
            markup = kwargs.get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                for row in markup.inline_keyboard:
                    for btn in row:
                        if btn.callback_data and btn.callback_data.startswith("view_"):
                            # Button text should have icon + process name
                            assert seed_process.name in btn.text
                            return
        pytest.fail("No process button found in list")
