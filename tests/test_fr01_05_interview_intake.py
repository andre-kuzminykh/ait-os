"""Tests for FR-1..FR-5: Interview Intake.

FR-1  Bot must support process-specific interview sessions via unique links.
FR-2  Bot must accept text responses.
FR-3  Bot must accept Telegram voice messages.
FR-4  Bot must accept Telegram audio/file uploads.
FR-5  Bot must store raw user inputs with timestamp, respondent and process context.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from bot.models import (
    Company,
    InterviewSession,
    Process,
    RawInput,
    Respondent,
)
from bot.states import ProcessStatus, SessionStatus
from tests.conftest import make_update


# ============================================================================
# FR-1: Process-specific interview sessions via unique links
# ============================================================================


class TestFR1_DeepLinkSessions:
    """FR-1: Bot must support process-specific interview sessions via unique links."""

    @pytest.mark.asyncio
    async def test_deep_link_starts_session(self, db_session, patch_db):
        """FR-1.1: Opening deep link /start process_<token> starts interview."""
        company = Company(name="TestCo")
        db_session.add(company)
        await db_session.flush()

        process = Process(
            company_id=company.id,
            name="Онбординг",
            status=ProcessStatus.CREATED,
        )
        db_session.add(process)
        await db_session.flush()

        respondent = Respondent(telegram_user_id=111222, display_name="Иван")
        db_session.add(respondent)
        await db_session.flush()

        session = InterviewSession(
            process_id=process.id,
            respondent_id=respondent.id,
            state=SessionStatus.STARTED,
        )
        db_session.add(session)
        await db_session.commit()

        token = session.token
        update, context = make_update(args=[f"process_{token}"])

        with patch("bot.handlers.callbacks.save_chat_context", new_callable=AsyncMock):
            from bot.handlers.start import cmd_start

            await cmd_start(update, context)

        update.message.reply_text.assert_called()
        call_text = update.message.reply_text.call_args[0][0]
        assert "Онбординг" in call_text

    @pytest.mark.asyncio
    async def test_invalid_deep_link_rejected(self, db_session, patch_db):
        """FR-1.2: Invalid deep link token returns error message."""
        # Ensure respondent exists
        respondent = Respondent(telegram_user_id=111222, display_name="Иван")
        db_session.add(respondent)
        await db_session.commit()

        update, context = make_update(args=["process_invalid_token_xyz"])

        from bot.handlers.start import cmd_start

        await cmd_start(update, context)

        update.message.reply_text.assert_called()
        call_text = update.message.reply_text.call_args[0][0]
        assert "недействительна" in call_text.lower() or "устарела" in call_text.lower()

    @pytest.mark.asyncio
    async def test_each_session_has_unique_token(self, db_session, seed_process, seed_respondent):
        """FR-1.3: Each interview session receives a unique token."""
        s1 = InterviewSession(
            process_id=seed_process.id,
            respondent_id=seed_respondent.id,
        )
        s2 = InterviewSession(
            process_id=seed_process.id,
            respondent_id=seed_respondent.id,
        )
        db_session.add_all([s1, s2])
        await db_session.commit()

        assert s1.token != s2.token
        assert len(s1.token) == 16
        assert len(s2.token) == 16

    @pytest.mark.asyncio
    async def test_session_bound_to_process(self, db_session, seed_session, seed_process):
        """FR-1.4: Session is correctly bound to its process."""
        assert seed_session.process_id == seed_process.id


# ============================================================================
# FR-2: Accept text responses
# ============================================================================


class TestFR2_TextInput:
    """FR-2: Bot must accept text responses."""

    @pytest.mark.asyncio
    async def test_text_message_saved(self, db_session, patch_db, seed_session, seed_process):
        """FR-2.1: Text message is stored as RawInput."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 99999
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        update, context = make_update(
            text="У нас процесс начинается с заявки от клиента",
            chat_id=chat_id,
        )

        with patch("bot.handlers.interview._process_input", new_callable=AsyncMock):
            from bot.handlers.interview import handle_text_message

            await handle_text_message(update, context)

        result = await db_session.execute(
            select(RawInput).where(RawInput.session_id == seed_session.id)
        )
        raw = result.scalar_one()
        assert raw.message_type == "text"
        assert "заявки от клиента" in raw.raw_text

    @pytest.mark.asyncio
    async def test_empty_text_ignored(self, db_session, patch_db, seed_session, seed_process):
        """FR-2.2: Empty text messages are ignored."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 88888
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        update, context = make_update(text="   ", chat_id=chat_id)
        update.message.text = "   "

        with patch("bot.handlers.interview._process_input", new_callable=AsyncMock) as mock_proc:
            from bot.handlers.interview import handle_text_message

            await handle_text_message(update, context)

        mock_proc.assert_not_called()

    @pytest.mark.asyncio
    async def test_text_without_session_prompts_start(self, patch_db):
        """FR-2.3: Text without active session prompts /start."""
        from bot.handlers.callbacks import _chat_contexts

        chat_id = 77777
        _chat_contexts.pop(chat_id, None)

        update, context = make_update(text="Тестовое сообщение", chat_id=chat_id)

        from bot.handlers.interview import handle_text_message

        await handle_text_message(update, context)

        update.message.reply_text.assert_called()
        call_text = update.message.reply_text.call_args[0][0]
        assert "/start" in call_text or "/new_process" in call_text


# ============================================================================
# FR-3: Accept Telegram voice messages
# ============================================================================


class TestFR3_VoiceInput:
    """FR-3: Bot must accept Telegram voice messages."""

    @pytest.mark.asyncio
    async def test_voice_transcribed_and_saved(
        self, db_session, patch_db, seed_session, seed_process
    ):
        """FR-3.1: Voice message is transcribed and stored as RawInput."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 99999
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        voice = MagicMock()
        voice.file_id = "voice_file_123"

        update, context = make_update(chat_id=chat_id, voice=voice)
        update.message.voice = voice

        with (
            patch(
                "bot.handlers.interview.transcribe_telegram_voice",
                new_callable=AsyncMock,
                return_value="Транскрипция голосового сообщения",
            ),
            patch("bot.handlers.interview._process_input", new_callable=AsyncMock),
        ):
            from bot.handlers.interview import handle_voice_message

            await handle_voice_message(update, context)

        result = await db_session.execute(
            select(RawInput).where(
                RawInput.session_id == seed_session.id,
                RawInput.message_type == "voice",
            )
        )
        raw = result.scalar_one()
        assert raw.transcript_text == "Транскрипция голосового сообщения"
        assert raw.file_ref == "voice_file_123"

    @pytest.mark.asyncio
    async def test_voice_transcription_failure(
        self, db_session, patch_db, seed_session, seed_process
    ):
        """FR-3.2: Failed transcription shows error to user."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 99998
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        voice = MagicMock()
        voice.file_id = "voice_bad"

        update, context = make_update(chat_id=chat_id, voice=voice)
        update.message.voice = voice

        with patch(
            "bot.handlers.interview.transcribe_telegram_voice",
            new_callable=AsyncMock,
            return_value="",
        ):
            from bot.handlers.interview import handle_voice_message

            await handle_voice_message(update, context)

        # Should tell user transcription failed (via bot.send_message or edit_message_text)
        bot = context.bot
        all_texts = []
        for call in bot.send_message.call_args_list:
            all_texts.append(call[1].get("text", ""))
        for call in bot.edit_message_text.call_args_list:
            all_texts.append(call[1].get("text", ""))
        assert any("не удалось" in t.lower() or "текстом" in t.lower() for t in all_texts)


# ============================================================================
# FR-4: Accept Telegram audio/file uploads
# ============================================================================


class TestFR4_AudioFileInput:
    """FR-4: Bot must accept Telegram audio/file uploads."""

    @pytest.mark.asyncio
    async def test_audio_file_accepted(
        self, db_session, patch_db, seed_session, seed_process
    ):
        """FR-4.1: Audio file with audio/* MIME type is accepted and transcribed."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 99997
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        doc = MagicMock()
        doc.mime_type = "audio/ogg"
        doc.file_id = "audio_doc_123"

        update, context = make_update(chat_id=chat_id, document=doc)
        update.message.document = doc
        update.message.voice = None

        with (
            patch(
                "bot.handlers.interview.transcribe_telegram_voice",
                new_callable=AsyncMock,
                return_value="Аудиозапись процесса",
            ),
            patch("bot.handlers.interview._process_input", new_callable=AsyncMock),
        ):
            from bot.handlers.interview import handle_document

            await handle_document(update, context)

        # Should have processed the audio (via bot.send_message for progress)
        context.bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_non_audio_file_rejected(
        self, db_session, patch_db, seed_session, seed_process
    ):
        """FR-4.2: Non-audio documents are rejected with a message."""
        from bot.handlers.callbacks import save_chat_context

        chat_id = 99996
        await save_chat_context(
            chat_id,
            {"session_id": seed_session.id, "process_id": seed_process.id},
        )

        doc = MagicMock()
        doc.mime_type = "application/pdf"

        update, context = make_update(chat_id=chat_id, document=doc)
        update.message.document = doc

        from bot.handlers.interview import handle_document

        await handle_document(update, context)

        call_text = update.message.reply_text.call_args[0][0]
        assert "аудио" in call_text.lower()


# ============================================================================
# FR-5: Store raw inputs with timestamp, respondent and process context
# ============================================================================


class TestFR5_RawInputStorage:
    """FR-5: Bot must store raw user inputs with timestamp, respondent and process context."""

    @pytest.mark.asyncio
    async def test_raw_input_has_timestamp(self, db_session, seed_session):
        """FR-5.1: RawInput has created_at timestamp."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Тест",
        )
        db_session.add(raw)
        await db_session.commit()
        await db_session.refresh(raw)

        assert raw.created_at is not None
        assert isinstance(raw.created_at, datetime)

    @pytest.mark.asyncio
    async def test_raw_input_linked_to_session(self, db_session, seed_session):
        """FR-5.2: RawInput is linked to interview session (respondent + process)."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Тест привязки",
            telegram_message_id=42,
        )
        db_session.add(raw)
        await db_session.commit()

        assert raw.session_id == seed_session.id

    @pytest.mark.asyncio
    async def test_raw_input_stores_telegram_message_id(self, db_session, seed_session):
        """FR-5.3: RawInput stores original Telegram message ID."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="ID теста",
            telegram_message_id=123456,
        )
        db_session.add(raw)
        await db_session.commit()
        await db_session.refresh(raw)

        assert raw.telegram_message_id == 123456

    @pytest.mark.asyncio
    async def test_multiple_inputs_per_session(self, db_session, seed_session):
        """FR-5.4: Multiple inputs can be stored for one session."""
        for i in range(3):
            db_session.add(
                RawInput(
                    session_id=seed_session.id,
                    message_type="text",
                    raw_text=f"Ответ {i + 1}",
                )
            )
        await db_session.commit()

        result = await db_session.execute(
            select(RawInput).where(RawInput.session_id == seed_session.id)
        )
        inputs = result.scalars().all()
        assert len(inputs) == 3
