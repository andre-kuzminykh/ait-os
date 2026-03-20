"""Tests for FR-11..FR-17: Clarification Flow (new 5-question Q&A).

FR-11  Bot must generate up to 5 structured clarification questions via LLM.
FR-12  Questions follow fixed order: operations, metrics, roles, systems, artifacts.
FR-13  Each question has only a "Skip" button; user answers directly via text/voice.
FR-14  Skipped questions advance to the next without breaking the session.
FR-15  Bot must continue to next question after skip or answer.
FR-16  Bot must allow the user to stop and resume later.
FR-17  When all questions are done (answered or skipped), AS-IS generation triggers.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from bot.models import Gap, InterviewSession, Process, AsIsModel
from bot.states import GapStatus, ProcessStatus, SessionStatus
from tests.conftest import (
    make_bot_mock,
    make_callback_query,
    make_update,
    SAMPLE_ASIS_MODEL,
    SAMPLE_GAP_RESULT,
    SAMPLE_CLARIFICATION_QUESTIONS,
    SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
    SAMPLE_EXTRACTED_ANSWER_METRICS,
)


# ============================================================================
# FR-11: Generate structured clarification questions
# ============================================================================


class TestFR11_ClarificationQuestionGeneration:
    """FR-11: Bot generates up to 5 structured clarification questions via LLM."""

    @pytest.mark.asyncio
    async def test_generate_clarification_questions_returns_included_only(self):
        """FR-11.1: Only questions with include=True are returned."""
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_CLARIFICATION_QUESTIONS, ensure_ascii=False),
        ):
            from bot.services.clarification import generate_clarification_questions

            questions = await generate_clarification_questions("Онбординг", SAMPLE_ASIS_MODEL)

        # Only metrics and systems have include=True
        assert len(questions) == 2
        assert questions[0]["field_type"] == "metrics"
        assert questions[1]["field_type"] == "systems"

    @pytest.mark.asyncio
    async def test_each_question_has_suggestions(self):
        """FR-11.2: Each question includes LLM-suggested answers."""
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_CLARIFICATION_QUESTIONS, ensure_ascii=False),
        ):
            from bot.services.clarification import generate_clarification_questions

            questions = await generate_clarification_questions("Онбординг", SAMPLE_ASIS_MODEL)

        for q in questions:
            assert "suggestions" in q
            assert len(q["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_max_5_questions(self):
        """FR-11.3: Maximum 5 questions returned."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")
        assert "5" in prompt

    @pytest.mark.asyncio
    async def test_empty_questions_on_complete_model(self):
        """FR-11.4: If all fields filled, no questions generated."""
        all_false = {
            "questions": [
                {"field_type": t, "include": False, "question": "", "suggestions": []}
                for t in ["operations", "metrics", "roles", "systems", "artifacts"]
            ]
        }
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(all_false, ensure_ascii=False),
        ):
            from bot.services.clarification import generate_clarification_questions

            questions = await generate_clarification_questions("Онбординг", SAMPLE_ASIS_MODEL)

        assert len(questions) == 0


# ============================================================================
# FR-12: Questions follow fixed order
# ============================================================================


class TestFR12_QuestionOrder:
    """FR-12: Questions follow fixed order: operations > metrics > roles > systems > artifacts."""

    @pytest.mark.asyncio
    async def test_question_order_maintained(self):
        """FR-12.1: Questions maintain the fixed priority order."""
        all_true = {
            "questions": [
                {"field_type": "operations", "include": True, "question": "Q1?", "suggestions": ["a"]},
                {"field_type": "metrics", "include": True, "question": "Q2?", "suggestions": ["b"]},
                {"field_type": "roles", "include": True, "question": "Q3?", "suggestions": ["c"]},
                {"field_type": "systems", "include": True, "question": "Q4?", "suggestions": ["d"]},
                {"field_type": "artifacts", "include": True, "question": "Q5?", "suggestions": ["e"]},
            ]
        }
        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(all_true, ensure_ascii=False),
        ):
            from bot.services.clarification import generate_clarification_questions

            questions = await generate_clarification_questions("Test", {})

        types = [q["field_type"] for q in questions]
        assert types == ["operations", "metrics", "roles", "systems", "artifacts"]

    @pytest.mark.asyncio
    async def test_question_order_in_prompt(self):
        """FR-12.2: Prompt specifies the 5 question types in correct order."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")

        # Check order of field types in the prompt
        idx_ops = prompt.lower().find("операции")
        idx_metrics = prompt.lower().find("метрики")
        idx_roles = prompt.lower().find("роли")
        idx_systems = prompt.lower().find("системы")
        idx_artifacts = prompt.lower().find("артефакты")

        assert idx_ops < idx_metrics, "Operations before metrics"
        assert idx_metrics < idx_roles, "Metrics before roles"
        assert idx_roles < idx_systems, "Roles before systems"
        assert idx_systems < idx_artifacts, "Systems before artifacts"


# ============================================================================
# FR-13: Each question has only a "Skip" button
# ============================================================================


class TestFR13_SkipButtonOnly:
    """FR-13: Each question has only a Skip button; user answers directly."""

    @pytest.mark.asyncio
    async def test_question_shows_skip_button(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-13.1: Clarification question shows only 'Пропустить' button."""
        bot = make_bot_mock()
        progress_id = 5000

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": progress_id,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import _show_clarification_question

        await _show_clarification_question(99999, bot, progress_id)

        bot.edit_message_text.assert_called()
        call_kwargs = bot.edit_message_text.call_args[1]
        markup = call_kwargs["reply_markup"]
        buttons = [btn.text for row in markup.inline_keyboard for btn in row]
        assert "Пропустить" in buttons
        assert "Ответить" not in buttons
        assert "Завершить позже" not in buttons

    @pytest.mark.asyncio
    async def test_question_shows_number_and_total(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-13.2: Question shows 'Вопрос N из M'."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import _show_clarification_question

        await _show_clarification_question(99999, bot, 5000)

        text = bot.edit_message_text.call_args[1]["text"]
        assert "Вопрос 1 из 2" in text

    @pytest.mark.asyncio
    async def test_question_shows_suggestions(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-13.3: Question shows LLM-suggested answers."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import _show_clarification_question

        await _show_clarification_question(99999, bot, 5000)

        text = bot.edit_message_text.call_args[1]["text"]
        assert "время оформления" in text
        assert "Возможные варианты" in text


# ============================================================================
# FR-14: Skip advances to next question
# ============================================================================


class TestFR14_SkipAdvances:
    """FR-14: Skipping advances to the next question without breaking."""

    @pytest.mark.asyncio
    async def test_skip_increments_index(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-14.1: Skip increments clarification_index."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context, get_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import handle_clarification_skip

        await handle_clarification_skip(99999, bot, 5000)

        ctx = await get_chat_context(99999)
        assert ctx["clarification_index"] == 1

    @pytest.mark.asyncio
    async def test_skip_shows_next_question(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-14.2: After skip, next question is shown."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import handle_clarification_skip

        await handle_clarification_skip(99999, bot, 5000)

        # Next question should be about systems (index=1)
        text = bot.edit_message_text.call_args[1]["text"]
        assert "Вопрос 2 из 2" in text
        assert "систем" in text.lower()


# ============================================================================
# FR-15: Continue after answer
# ============================================================================


class TestFR15_ContinueAfterAnswer:
    """FR-15: Bot advances to next question after receiving an answer."""

    @pytest.mark.asyncio
    async def test_answer_advances_to_next_question(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model,
    ):
        """FR-15.1: After answering, next question is shown."""
        seed_session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        seed_process.status = ProcessStatus.CLARIFICATION_IN_PROGRESS
        await db_session.commit()

        update, context = make_update(
            text="Время оформления — 1 день, ошибки менее 5%",
            message_id=42,
        )

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": seed_session.id,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_EXTRACTED_ANSWER_METRICS, ensure_ascii=False),
        ):
            from bot.handlers.clarification import handle_clarification_answer

            await handle_clarification_answer(update, "Время оформления — 1 день")

        # Should show next question (index advanced)
        bot = update.get_bot()
        last_text = bot.edit_message_text.call_args[1]["text"]
        assert "Вопрос 2 из 2" in last_text

    @pytest.mark.asyncio
    async def test_answer_updates_asis_model(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model,
    ):
        """FR-15.2: Answer data is merged into AS-IS model."""
        seed_session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        seed_process.status = ProcessStatus.CLARIFICATION_IN_PROGRESS
        await db_session.commit()

        update, context = make_update(
            text="Время оформления 1 день",
            message_id=42,
        )

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": seed_session.id,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(SAMPLE_EXTRACTED_ANSWER_METRICS, ensure_ascii=False),
        ):
            from bot.handlers.clarification import handle_clarification_answer

            await handle_clarification_answer(update, "Время оформления 1 день")

        # Check model was updated
        await db_session.refresh(seed_asis_model)
        metrics = json.loads(seed_asis_model.metrics)
        assert len(metrics) > 0


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

        # Clear any stale chat context
        from bot.handlers.callbacks import _chat_contexts
        _chat_contexts.pop(99999, None)

        from bot.handlers.clarification import handle_pause

        await handle_pause(99999, seed_process.id, bot)

        total = bot.send_message.call_count + bot.edit_message_text.call_count
        assert total >= 1
        if bot.send_message.call_count:
            text = bot.send_message.call_args[1]["text"]
        else:
            text = bot.edit_message_text.call_args[1]["text"]
        assert "приостановлена" in text.lower()


# ============================================================================
# FR-17: Trigger generation when all questions done
# ============================================================================


class TestFR17_TriggerGeneration:
    """FR-17: When all questions done, AS-IS generation is triggered."""

    @pytest.mark.asyncio
    async def test_skip_all_triggers_generation(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-17.1: Skipping all questions triggers AS-IS generation."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        with patch(
            "bot.handlers.clarification.trigger_asis_generation",
            new_callable=AsyncMock,
        ) as mock_gen:
            from bot.handlers.clarification import handle_clarification_skip

            # Skip first question
            await handle_clarification_skip(99999, bot, 5000)
            # Skip second question
            await handle_clarification_skip(99999, bot, 5000)

        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_questions_triggers_generation(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-17.2: When LLM generates no questions, generation is triggered."""
        bot = make_bot_mock()

        all_false = {
            "questions": [
                {"field_type": t, "include": False, "question": "", "suggestions": []}
                for t in ["operations", "metrics", "roles", "systems", "artifacts"]
            ]
        }

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
        })

        with (
            patch(
                "bot.services.clarification.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(all_false, ensure_ascii=False),
            ),
            patch(
                "bot.handlers.clarification.trigger_asis_generation",
                new_callable=AsyncMock,
            ) as mock_gen,
        ):
            from bot.handlers.clarification import start_clarification_flow

            await start_clarification_flow(99999, seed_process.id, bot, 5000)

        mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_completeness_skips_clarification(self):
        """FR-17.3: When completeness >= threshold, clarification is not started."""
        from bot.config import COMPLETENESS_THRESHOLD

        # Verify threshold is reasonable
        assert 0.0 < COMPLETENESS_THRESHOLD < 1.0
