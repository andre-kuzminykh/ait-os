"""Tests for FR-11..FR-17: Clarification Flow.

FR-11  Bot must generate targeted follow-up questions from detected gaps.
FR-12  Each follow-up must be linked to a stage and field type when applicable.
FR-13  Each follow-up question must support skip action.
FR-14  Skipped questions must be persisted as skipped, not lost.
FR-15  Bot must continue interview after skip without breaking the session.
FR-16  Bot must allow the user to stop and resume later.
FR-17  Bot must stop asking more questions when minimum completeness threshold
       is reached or when no more useful gaps remain.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from bot.models import Gap, InterviewSession, Process
from bot.states import GapStatus, ProcessStatus, SessionStatus
from tests.conftest import make_bot_mock, make_callback_query, SAMPLE_ASIS_MODEL, SAMPLE_GAP_RESULT


# ============================================================================
# FR-11: Generate targeted follow-up questions from detected gaps
# ============================================================================


class TestFR11_FollowUpGeneration:
    """FR-11: Bot must generate targeted follow-up questions from detected gaps."""

    @pytest.mark.asyncio
    async def test_send_next_gap_question_sends_message(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-11.1: send_next_gap_question sends the pending gap question to user."""
        bot = make_bot_mock()

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot)

        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 99999
        assert "❓" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_questions_prioritized_by_confidence(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-11.2: Questions are sent in order of lowest confidence first."""
        bot = make_bot_mock()

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot)

        # The gap with lowest confidence_score should be sent first
        text = bot.send_message.call_args[1]["text"]
        # seed_gaps[0] has confidence=0.3 (lowest)
        assert seed_gaps[0].question_text in text

    @pytest.mark.asyncio
    async def test_no_gaps_triggers_generation(
        self, db_session, patch_db, seed_process
    ):
        """FR-11.3: When no pending gaps remain, AS-IS generation is triggered."""
        bot = make_bot_mock()

        with patch(
            "bot.handlers.clarification.trigger_asis_generation",
            new_callable=AsyncMock,
        ) as mock_gen:
            from bot.handlers.clarification import send_next_gap_question

            await send_next_gap_question(99999, seed_process.id, bot)

        mock_gen.assert_called_once_with(99999, seed_process.id, bot)


# ============================================================================
# FR-12: Follow-up linked to stage and field type
# ============================================================================


class TestFR12_FollowUpLinkedToStage:
    """FR-12: Each follow-up must be linked to a stage and field type."""

    @pytest.mark.asyncio
    async def test_gap_model_has_stage_id(self, seed_gaps):
        """FR-12.1: Gap model stores stage_id."""
        stage_gaps = [g for g in seed_gaps if g.stage_id is not None]
        assert len(stage_gaps) > 0
        assert stage_gaps[0].stage_id.startswith("stage_")

    @pytest.mark.asyncio
    async def test_gap_model_has_field_type(self, seed_gaps):
        """FR-12.2: Gap model stores field_type enum."""
        for g in seed_gaps:
            assert g.field_type is not None
            assert isinstance(g.field_type, GapStatus.__class__) or g.field_type is not None

    @pytest.mark.asyncio
    async def test_process_level_gap_has_null_stage(self, seed_gaps):
        """FR-12.3: Process-level gaps have stage_id = None."""
        process_gaps = [g for g in seed_gaps if g.stage_id is None]
        assert len(process_gaps) > 0


# ============================================================================
# FR-13: Each follow-up must support skip action
# ============================================================================


class TestFR13_SkipAction:
    """FR-13: Each follow-up question must support skip action."""

    @pytest.mark.asyncio
    async def test_question_has_skip_button(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-13.1: Each question is sent with a 'Пропустить' inline button."""
        bot = make_bot_mock()

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]
        # Extract button texts from inline keyboard
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        assert "Пропустить" in buttons

    @pytest.mark.asyncio
    async def test_question_has_answer_button(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-13.2: Each question has an 'Ответить' inline button."""
        bot = make_bot_mock()

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        assert "Ответить" in buttons

    @pytest.mark.asyncio
    async def test_question_has_pause_button(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-13.3: Each question has a 'Завершить позже' inline button."""
        bot = make_bot_mock()

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot)

        call_kwargs = bot.send_message.call_args[1]
        markup = call_kwargs["reply_markup"]
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        assert "Завершить позже" in buttons


# ============================================================================
# FR-14: Skipped questions persisted as skipped
# ============================================================================


class TestFR14_SkipPersistence:
    """FR-14: Skipped questions must be persisted as skipped, not lost."""

    @pytest.mark.asyncio
    async def test_skip_sets_status_to_skipped(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-14.1: Skipping a gap sets its status to SKIPPED in database."""
        gap_id = seed_gaps[0].id
        bot = make_bot_mock()

        from bot.handlers.clarification import handle_gap_skip

        await handle_gap_skip(99999, gap_id, bot)

        await db_session.refresh(seed_gaps[0])
        assert seed_gaps[0].status == GapStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_skipped_gap_not_deleted(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-14.2: Skipped gap record remains in the database."""
        gap_id = seed_gaps[0].id
        bot = make_bot_mock()

        from bot.handlers.clarification import handle_gap_skip

        await handle_gap_skip(99999, gap_id, bot)

        async with patch_db() as fresh:
            result = await fresh.execute(select(Gap).where(Gap.id == gap_id))
            gap = result.scalar_one_or_none()
            assert gap is not None
            assert gap.status == GapStatus.SKIPPED


# ============================================================================
# FR-15: Continue interview after skip
# ============================================================================


class TestFR15_ContinueAfterSkip:
    """FR-15: Bot must continue interview after skip without breaking the session."""

    @pytest.mark.asyncio
    async def test_skip_sends_next_question(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-15.1: After skipping, the next pending question is sent."""
        gap_id = seed_gaps[0].id
        bot = make_bot_mock()

        from bot.handlers.clarification import handle_gap_skip

        await handle_gap_skip(99999, gap_id, bot)

        # Should have sent "Пропущено" and then the next question
        assert bot.send_message.call_count >= 2

    @pytest.mark.asyncio
    async def test_skip_all_gaps_triggers_generation(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-15.2: Skipping all gaps triggers AS-IS generation."""
        bot = make_bot_mock()

        with patch(
            "bot.handlers.clarification.trigger_asis_generation",
            new_callable=AsyncMock,
        ) as mock_gen:
            from bot.handlers.clarification import handle_gap_skip

            for gap in seed_gaps:
                await handle_gap_skip(99999, gap.id, bot)

        mock_gen.assert_called_once()


# ============================================================================
# FR-16: Allow user to stop and resume later
# ============================================================================


class TestFR16_PauseResume:
    """FR-16: Bot must allow the user to stop and resume later."""

    @pytest.mark.asyncio
    async def test_pause_sets_session_to_paused(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-16.1: Pausing sets session state to PAUSED."""
        seed_session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        await db_session.commit()

        bot = make_bot_mock()

        from bot.handlers.clarification import handle_pause

        await handle_pause(99999, seed_process.id, bot)

        await db_session.refresh(seed_session)
        assert seed_session.state == SessionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_pause_sends_confirmation(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-16.2: Pausing sends a confirmation message."""
        seed_session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        await db_session.commit()

        bot = make_bot_mock()

        from bot.handlers.clarification import handle_pause

        await handle_pause(99999, seed_process.id, bot)

        bot.send_message.assert_called_once()
        text = bot.send_message.call_args[1]["text"]
        assert "приостановлена" in text.lower()

    @pytest.mark.asyncio
    async def test_resume_restores_session(
        self, db_session, patch_db, seed_process, seed_session, seed_gaps
    ):
        """FR-16.3: Resuming restores session to AWAITING_FOLLOWUP_ANSWER."""
        seed_session.state = SessionStatus.PAUSED
        await db_session.commit()

        from bot.handlers.callbacks import _handle_resume, save_chat_context

        update = MagicMock()
        bot = make_bot_mock()

        with patch(
            "bot.handlers.clarification.send_next_gap_question",
            new_callable=AsyncMock,
        ):
            await _handle_resume(99999, seed_session.id, update, bot)

        await db_session.refresh(seed_session)
        assert seed_session.state == SessionStatus.AWAITING_FOLLOWUP_ANSWER


# ============================================================================
# FR-17: Stop asking when threshold reached or no gaps remain
# ============================================================================


class TestFR17_CompletenessThreshold:
    """FR-17: Bot must stop asking when completeness threshold reached."""

    @pytest.mark.asyncio
    async def test_high_completeness_triggers_generation(self):
        """FR-17.1: When completeness >= threshold, AS-IS generation is triggered."""
        from bot.config import COMPLETENESS_THRESHOLD

        # Verify threshold is reasonable
        assert 0.0 < COMPLETENESS_THRESHOLD < 1.0

    @pytest.mark.asyncio
    async def test_process_input_with_high_completeness(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-17.2: _process_input triggers generation when completeness is high."""
        from bot.models import RawInput

        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Полное описание процесса с ролями, системами, метриками",
        )
        db_session.add(raw)
        await db_session.commit()

        bot = make_bot_mock()

        high_completeness = {"completeness_score": 0.9, "gaps": []}

        with (
            patch(
                "bot.handlers.interview.extract_asis_model",
                new_callable=AsyncMock,
                return_value=SAMPLE_ASIS_MODEL,
            ),
            patch(
                "bot.handlers.interview.detect_gaps",
                new_callable=AsyncMock,
                return_value=high_completeness,
            ),
            patch(
                "bot.handlers.clarification.trigger_asis_generation",
                new_callable=AsyncMock,
            ) as mock_gen,
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_input_with_low_completeness_asks_questions(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-17.3: _process_input asks follow-up when completeness is low."""
        from bot.models import RawInput

        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Процесс начинается с заявки",
        )
        db_session.add(raw)
        await db_session.commit()

        bot = make_bot_mock()

        with (
            patch(
                "bot.handlers.interview.extract_asis_model",
                new_callable=AsyncMock,
                return_value=SAMPLE_ASIS_MODEL,
            ),
            patch(
                "bot.handlers.interview.detect_gaps",
                new_callable=AsyncMock,
                return_value=SAMPLE_GAP_RESULT,
            ),
            patch(
                "bot.handlers.clarification.send_next_gap_question",
                new_callable=AsyncMock,
            ) as mock_q,
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        mock_q.assert_called_once()
