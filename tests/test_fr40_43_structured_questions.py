"""Tests for FR-40..FR-48: structured questions, monotonic completeness,
single-message editing, separate LLM calls, editable prompts/messages,
progress bar %, URL handling, and greeting overwrite."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tests.conftest import (
    BotMock,
    SAMPLE_ASIS_MODEL,
    SAMPLE_GAP_RESULT,
    SAMPLE_GAP_RESULT_HIGH,
    SAMPLE_MERMAID,
    SAMPLE_NARRATIVE,
    SAMPLE_OPPORTUNITIES,
    make_bot_mock,
    make_update,
)
from bot.models import AsIsModel, InterviewSession, Process, RawInput
from bot.states import GapStatus, ProcessStatus, SessionStatus


# ============================================================================
# FR-40: Completeness score never decreases
# ============================================================================


class TestFR40_MonotonicCompleteness:
    """FR-40: completeness_score must never decrease."""

    @pytest.mark.asyncio
    async def test_completeness_does_not_decrease(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.1: If LLM returns lower score, stored score stays at max."""
        # Set existing score to 0.5 so it doesn't trigger AS-IS generation
        seed_asis_model.completeness_score = 0.5

        # Prepare raw input
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Дополнительная информация.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        # LLM returns lower completeness (0.30) and some gaps
        lower_gap_result = {
            "completeness_score": 0.30,
            "gaps": [
                {
                    "stage_id": "stage_1",
                    "field_type": "metrics",
                    "question": "Какие метрики?",
                    "confidence": 0.3,
                }
            ],
        }

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(lower_gap_result, ensure_ascii=False),
            ),
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        # Verify completeness didn't decrease from 0.5
        await db_session.refresh(seed_asis_model)
        assert seed_asis_model.completeness_score >= 0.5

    @pytest.mark.asyncio
    async def test_completeness_can_increase(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.2: Higher LLM scores are accepted."""
        seed_asis_model.completeness_score = 0.4
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Больше деталей.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        higher_gap_result = {
            "completeness_score": 0.75,
            "gaps": [],
        }

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(higher_gap_result, ensure_ascii=False),
            ),
            patch(
                "bot.handlers.clarification.trigger_asis_generation",
                new_callable=AsyncMock,
            ),
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        await db_session.refresh(seed_asis_model)
        assert seed_asis_model.completeness_score >= 0.75

    @pytest.mark.asyncio
    async def test_display_score_uses_max(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.3: Displayed percentage uses max(old, new), never shows decrease."""
        # Set to 0.50 (below threshold 0.6 so it won't trigger generation)
        seed_asis_model.completeness_score = 0.50
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Ещё данные.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        # LLM returns lower score
        lower_result = {
            "completeness_score": 0.35,
            "gaps": [
                {
                    "stage_id": "stage_1",
                    "field_type": "roles",
                    "question": "Кто?",
                    "confidence": 0.3,
                }
            ],
        }

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(lower_result, ensure_ascii=False),
            ),
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        # Check that displayed percentage never shows 35%
        for call in bot.edit_message_text.call_args_list:
            text = call[1].get("text", "")
            if "Полнота:" in text:
                # Should show 50%, not 35%
                assert "50%" in text
                assert "35%" not in text


# ============================================================================
# FR-41: Questions only for empty fields per stage
# ============================================================================


class TestFR41_StructuredGapQuestions:
    """FR-41: Gap questions must only target actually empty fields."""

    @pytest.mark.asyncio
    async def test_gap_prompt_mentions_stage_fields(self):
        """FR-41.1: The gap detector prompt instructs LLM to check per-stage fields."""
        from bot.prompts import load_prompt
        prompt = load_prompt("gap_detector")

        # Prompt must mention checking each stage for these fields
        assert "owner_role" in prompt or "Роль" in prompt
        assert "systems" in prompt or "Система" in prompt
        assert "metrics" in prompt or "Метрик" in prompt
        assert "inputs" in prompt or "Артефакт" in prompt
        assert "outputs" in prompt or "выход" in prompt

    @pytest.mark.asyncio
    async def test_gap_prompt_requires_empty_fields_only(self):
        """FR-41.2: Prompt instructs to ask ONLY about empty fields."""
        from bot.prompts import load_prompt
        prompt = load_prompt("gap_detector")

        assert "пуст" in prompt.lower() or "отсутств" in prompt.lower()

    @pytest.mark.asyncio
    async def test_gap_prompt_has_max_5_questions(self):
        """FR-41.3: Max 5 questions per call."""
        from bot.prompts import load_prompt
        prompt = load_prompt("gap_detector")

        assert "5" in prompt

    @pytest.mark.asyncio
    async def test_prompts_loaded_from_files(self):
        """FR-41.4: All prompts are loaded from separate .txt files."""
        from bot.prompts import load_prompt

        for name in ["extractor", "gap_detector", "generator", "mermaid", "opportunities"]:
            prompt = load_prompt(name)
            assert len(prompt) > 50, f"Prompt '{name}' should be non-trivial"


# ============================================================================
# FR-42: Question priority order
# ============================================================================


class TestFR42_QuestionPriority:
    """FR-42: Questions prioritized: steps > roles > systems > metrics > artifacts."""

    @pytest.mark.asyncio
    async def test_priority_order_in_prompt(self):
        """FR-42.1: Gap detector prompt specifies priority order in priority section."""
        from bot.prompts import load_prompt
        prompt = load_prompt("gap_detector")

        # Find the priority section (numbered list 1-5)
        priority_section = prompt[prompt.find("Группируй"):]
        priority_lower = priority_section.lower()

        # Check that priority items appear in the correct order
        idx_steps = priority_lower.find("шаг")
        idx_roles = priority_lower.find("рол")
        idx_systems = priority_lower.find("систем")
        idx_metrics = priority_lower.find("метрик")
        idx_artifacts = priority_lower.find("артефакт")

        assert idx_steps > -1, "Steps mentioned in priority section"
        assert idx_roles > -1, "Roles mentioned in priority section"

        assert idx_steps < idx_roles, "Steps must come before roles"
        assert idx_roles < idx_systems, "Roles must come before systems"
        assert idx_systems < idx_metrics, "Systems must come before metrics"
        assert idx_metrics < idx_artifacts, "Metrics must come before artifacts"


# ============================================================================
# FR-43: Separate LLM calls for narrative, diagram, and opportunities
# ============================================================================


class TestFR43_SeparateLLMCalls:
    """FR-43: AS-IS generation uses 3 separate LLM calls."""

    @pytest.mark.asyncio
    async def test_three_separate_llm_calls(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path,
    ):
        """FR-43.1: trigger_asis_generation makes 3 separate LLM calls."""
        bot = make_bot_mock()

        narrative_mock = AsyncMock(
            return_value=json.dumps(SAMPLE_NARRATIVE, ensure_ascii=False)
        )
        mermaid_mock = AsyncMock(return_value=SAMPLE_MERMAID)
        opps_mock = AsyncMock(
            return_value=json.dumps(
                {"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False
            )
        )

        with (
            patch("bot.services.generator.chat", narrative_mock),
            patch("bot.services.mermaid.chat", mermaid_mock),
            patch("bot.services.opportunities.chat", opps_mock),
            patch("bot.services.publisher.PAGES_DIR", tmp_path),
        ):
            from bot.handlers.clarification import trigger_asis_generation

            await trigger_asis_generation(99999, seed_process.id, bot)

        # Each must be called at least once (separately)
        narrative_mock.assert_called()
        mermaid_mock.assert_called()
        opps_mock.assert_called()

        # Verify they were called with different system prompts
        narrative_prompt = narrative_mock.call_args_list[0][0][0]
        mermaid_prompt = mermaid_mock.call_args_list[0][0][0]
        opps_prompt = opps_mock.call_args_list[0][0][0]

        assert narrative_prompt != mermaid_prompt
        assert mermaid_prompt != opps_prompt

    @pytest.mark.asyncio
    async def test_result_contains_url(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path,
    ):
        """FR-43.2: Final message contains the published page URL."""
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
                return_value=json.dumps(
                    {"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False
                ),
            ),
        ):
            from bot.handlers.clarification import trigger_asis_generation

            await trigger_asis_generation(99999, seed_process.id, bot)

        # Check that final message (send or edit) contains the URL
        all_calls = (
            list(bot.send_message.call_args_list)
            + list(bot.edit_message_text.call_args_list)
        )

        found_url = False
        for call in all_calls:
            text = call[1].get("text", "")
            if ".html" in text and "AS-IS" in text:
                found_url = True
                break

        assert found_url, "Final message must contain AS-IS page URL"


# ============================================================================
# FR-35 (updated): All progress via single message edit
# ============================================================================


class TestFR35_SingleMessageEdit:
    """FR-35: All progress and questions are shown by editing one message."""

    @pytest.mark.asyncio
    async def test_gap_question_edits_progress_message(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-35.1: Gap question replaces progress message via edit."""
        bot = make_bot_mock()
        progress_msg_id = 5000

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot, progress_msg_id)

        # Should have edited the progress message, not sent a new one
        bot.edit_message_text.assert_called()
        edit_kwargs = bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == progress_msg_id
        assert "❓" in edit_kwargs["text"]

    @pytest.mark.asyncio
    async def test_skip_edits_same_message(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-35.2: Skipping a question edits the same message to next question."""
        gap_id = seed_gaps[0].id
        bot = make_bot_mock()
        msg_id = 6000

        from bot.handlers.clarification import handle_gap_skip

        await handle_gap_skip(99999, gap_id, bot, msg_id)

        # Should have edited message_id=6000 to the next question
        bot.edit_message_text.assert_called()
        edit_kwargs = bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == msg_id

    @pytest.mark.asyncio
    async def test_answer_prompt_edits_message(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-35.3: 'Answer' prompt edits the existing bot message."""
        gap_id = seed_gaps[0].id
        bot = make_bot_mock()

        # Set up chat context with bot_message_id
        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "pending_gap_id": gap_id,
            "bot_message_id": 7000,
        })

        from bot.handlers.callbacks import _handle_answer_prompt

        await _handle_answer_prompt(99999, gap_id, bot)

        # Should edit, not send new
        bot.edit_message_text.assert_called()
        assert bot.edit_message_text.call_args[1]["message_id"] == 7000

    @pytest.mark.asyncio
    async def test_pause_edits_message(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-35.4: Pause edits the existing bot message."""
        seed_session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        await db_session.commit()

        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": seed_session.id,
            "process_id": seed_process.id,
            "bot_message_id": 8000,
        })

        from bot.handlers.clarification import handle_pause

        await handle_pause(99999, seed_process.id, bot)

        bot.edit_message_text.assert_called()
        text = bot.edit_message_text.call_args[1]["text"]
        assert "приостановлена" in text.lower()

    @pytest.mark.asyncio
    async def test_no_new_messages_during_gap_flow(
        self, db_session, patch_db, seed_process, seed_gaps
    ):
        """FR-35.5: During gap question flow, bot.send_message is NOT called."""
        bot = make_bot_mock()
        progress_msg_id = 9000

        from bot.handlers.clarification import send_next_gap_question

        await send_next_gap_question(99999, seed_process.id, bot, progress_msg_id)

        # send_message should NOT be called when progress_id is provided
        bot.send_message.assert_not_called()


# ============================================================================
# FR-36 (updated): User messages deleted, bot edits one message
# ============================================================================


# ============================================================================
# FR-44: Prompts in separate .txt files
# ============================================================================


class TestFR44_PromptsInFiles:
    """FR-44: All LLM prompts are loaded from bot/prompts/*.txt files."""

    @pytest.mark.asyncio
    async def test_all_prompt_files_exist(self):
        """FR-44.1: All 5 prompt files exist and are non-trivial."""
        from bot.prompts import load_prompt

        for name in ["extractor", "gap_detector", "generator", "mermaid", "opportunities"]:
            prompt = load_prompt(name)
            assert len(prompt) > 50, f"Prompt '{name}' should be non-trivial"

    @pytest.mark.asyncio
    async def test_services_use_prompt_files(self):
        """FR-44.2: Service modules load prompts from files, not inline strings."""
        from bot.services.extractor import SYSTEM_PROMPT as ext_prompt
        from bot.services.gap_detector import SYSTEM_PROMPT as gap_prompt
        from bot.services.generator import SYSTEM_PROMPT as gen_prompt
        from bot.services.mermaid import SYSTEM_PROMPT as merm_prompt
        from bot.services.opportunities import SYSTEM_PROMPT as opp_prompt
        from bot.prompts import load_prompt

        # Each service prompt must match the file content
        assert ext_prompt == load_prompt("extractor")
        assert gap_prompt == load_prompt("gap_detector")
        assert gen_prompt == load_prompt("generator")
        assert merm_prompt == load_prompt("mermaid")
        assert opp_prompt == load_prompt("opportunities")


# ============================================================================
# FR-45: Status messages in bot/messages.py
# ============================================================================


class TestFR45_MessagesModule:
    """FR-45: All user-facing status messages in bot/messages.py."""

    @pytest.mark.asyncio
    async def test_messages_module_has_all_keys(self):
        """FR-45.1: All key status messages exist."""
        import bot.messages as bmsg

        required = [
            "INPUT_SAVED", "INPUT_SAVED_DETAIL",
            "VOICE_RECEIVED", "VOICE_RECEIVED_DETAIL", "VOICE_FAILED",
            "EXTRACTING_STRUCTURE", "EXTRACTING_STRUCTURE_DETAIL",
            "EVALUATING_COMPLETENESS", "EVALUATING_COMPLETENESS_DETAIL",
            "COMPLETENESS_READY", "COMPLETENESS_PARTIAL",
            "GEN_NARRATIVE", "GEN_NARRATIVE_DETAIL",
            "GEN_DIAGRAM", "GEN_DIAGRAM_DETAIL",
            "GEN_PUBLISH", "GEN_PUBLISH_DETAIL",
            "GEN_OPPORTUNITIES", "GEN_OPPORTUNITIES_DETAIL",
            "ASIS_READY_TEXT", "ASIS_READY_TEXT_NO_URL",
            "BTN_OPEN_ASIS", "BTN_ANSWER", "BTN_SKIP", "BTN_PAUSE",
            "BTN_CONTINUE_OPPS",
            "SESSION_PAUSED", "ANSWER_PROMPT",
            "GAP_ANSWER_SAVED", "GAP_ANSWER_SAVED_DETAIL",
            "ANALYSIS_FAILED", "GEN_NO_DATA", "GEN_NO_OPPS",
            "NO_CONTEXT", "AUDIO_ONLY",
        ]
        for key in required:
            assert hasattr(bmsg, key), f"bot.messages missing: {key}"
            assert getattr(bmsg, key), f"bot.messages.{key} is empty"

    @pytest.mark.asyncio
    async def test_asis_ready_text_has_placeholders(self):
        """FR-45.2: ASIS_READY_TEXT has {name} and {url} placeholders."""
        import bot.messages as bmsg

        assert "{name}" in bmsg.ASIS_READY_TEXT
        assert "{url}" in bmsg.ASIS_READY_TEXT
        # Should not crash when formatted
        result = bmsg.ASIS_READY_TEXT.format(name="Test", url="https://example.com")
        assert "Test" in result
        assert "https://example.com" in result


# ============================================================================
# FR-46: Progress bar shows % towards HTML (6 steps)
# ============================================================================


class TestFR46_ProgressBarPercentage:
    """FR-46: Progress bar uses 6 total steps (input→extract→completeness→narrative→diagram→publish)."""

    @pytest.mark.asyncio
    async def test_total_steps_is_6(self):
        """FR-46.1: Both interview and clarification use TOTAL_STEPS=6."""
        from bot.handlers.interview import TOTAL_STEPS
        from bot.handlers.clarification import TOTAL_STEPS as TOTAL_STEPS_2

        assert TOTAL_STEPS == 6
        assert TOTAL_STEPS_2 == 6

    @pytest.mark.asyncio
    async def test_step_1_is_16_percent(self):
        """FR-46.2: Step 1/6 = 16%."""
        from bot.handlers.progress import loading_bar
        bar = loading_bar(1, 6)
        assert "16%" in bar

    @pytest.mark.asyncio
    async def test_step_3_is_50_percent(self):
        """FR-46.3: Step 3/6 = 50%."""
        from bot.handlers.progress import loading_bar
        bar = loading_bar(3, 6)
        assert "50%" in bar

    @pytest.mark.asyncio
    async def test_step_6_is_100_percent(self):
        """FR-46.4: Step 6/6 = 100%."""
        from bot.handlers.progress import loading_bar
        bar = loading_bar(6, 6)
        assert "100%" in bar


# ============================================================================
# FR-47: localhost URL handling
# ============================================================================


class TestFR47_UrlHandling:
    """FR-47: localhost URLs shown as text; https URLs use inline button."""

    @pytest.mark.asyncio
    async def test_localhost_url_no_inline_button(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path,
    ):
        """FR-47.1: localhost URL does not create an inline url= button."""
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
                return_value=json.dumps(
                    {"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False
                ),
            ),
        ):
            from bot.handlers.clarification import trigger_asis_generation
            await trigger_asis_generation(99999, seed_process.id, bot)

        # Check that no inline button has url= with localhost
        all_calls = (
            list(bot.send_message.call_args_list)
            + list(bot.edit_message_text.call_args_list)
        )
        for call in all_calls:
            markup = call[1].get("reply_markup")
            if markup and hasattr(markup, "inline_keyboard"):
                for row in markup.inline_keyboard:
                    for btn in row:
                        if hasattr(btn, "url") and btn.url:
                            assert not btn.url.startswith("http://localhost"), \
                                f"localhost URL must not be used in inline button: {btn.url}"

    @pytest.mark.asyncio
    async def test_url_shown_in_text(
        self, db_session, patch_db, seed_process, seed_asis_model, tmp_path,
    ):
        """FR-47.2: The URL is always present in message text."""
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
                return_value=json.dumps(
                    {"opportunities": SAMPLE_OPPORTUNITIES}, ensure_ascii=False
                ),
            ),
        ):
            from bot.handlers.clarification import trigger_asis_generation
            await trigger_asis_generation(99999, seed_process.id, bot)

        all_calls = (
            list(bot.send_message.call_args_list)
            + list(bot.edit_message_text.call_args_list)
        )
        found_url = any(
            ".html" in call[1].get("text", "")
            for call in all_calls
        )
        assert found_url, "URL must appear in message text"


class TestFR36_CleanChat:
    """FR-36: User messages are deleted; bot only edits its single message."""

    @pytest.mark.asyncio
    async def test_user_text_deleted_bot_edits(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-36.1: User text message is deleted, bot edits existing message."""
        seed_session.state = SessionStatus.AWAITING_INITIAL_RESPONSE
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        update, context = make_update(
            text="Описание процесса",
            message_id=42,
        )

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": seed_session.id,
            "process_id": seed_process.id,
            "bot_message_id": 3000,
        })

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False),
            ),
        ):
            from bot.handlers.interview import handle_text_message

            await handle_text_message(update, context)

        # User message must be deleted
        context.bot.delete_message.assert_any_call(chat_id=99999, message_id=42)

        # Bot should edit existing message (bot_message_id=3000), not send new
        # At least one edit should target message_id=3000
        found_edit = False
        for call in context.bot.edit_message_text.call_args_list:
            if call[1].get("message_id") == 3000:
                found_edit = True
                break
        assert found_edit, "Bot should edit existing message_id=3000"


# ============================================================================
# FR-48: Greeting message overwritten by first progress step
# ============================================================================


class TestFR48_GreetingOverwrite:
    """FR-48: 'Process created' greeting is saved as bot_message_id and
    overwritten by the first progress step."""

    @pytest.mark.asyncio
    async def test_new_process_greeting_saved_as_bot_message_id(
        self, db_session, patch_db, seed_company, seed_respondent
    ):
        """FR-48.1: handle_new_process_name stores greeting message_id in context."""
        bot = make_bot_mock()

        from bot.handlers.start import handle_new_process_name
        from bot.handlers.callbacks import save_chat_context, get_chat_context

        # Set up context as if user clicked "+"
        await save_chat_context(99999, {
            "awaiting_process_name": True,
            "messages_to_delete": [],
            "telegram_user_id": seed_respondent.telegram_user_id,
        })

        await handle_new_process_name(
            bot, 99999, "Тестовый процесс",
            seed_respondent.telegram_user_id, 42,
        )

        ctx = await get_chat_context(99999)
        assert ctx is not None
        assert "bot_message_id" in ctx, "Greeting message_id must be saved in context"
        # The bot_message_id should be the message_id returned by send_message
        assert ctx["bot_message_id"] > 0

    @pytest.mark.asyncio
    async def test_greeting_overwritten_by_progress(
        self, db_session, patch_db, seed_process, seed_session
    ):
        """FR-48.2: When user sends text, the greeting is edited (not a new message)."""
        seed_session.state = SessionStatus.AWAITING_INITIAL_RESPONSE
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        update, context = make_update(text="Описание процесса", message_id=50)

        # Simulate greeting message already in context
        from bot.handlers.callbacks import save_chat_context, get_chat_context
        greeting_msg_id = 2000
        await save_chat_context(99999, {
            "session_id": seed_session.id,
            "process_id": seed_process.id,
            "bot_message_id": greeting_msg_id,
        })

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_GAP_RESULT, ensure_ascii=False),
            ),
        ):
            from bot.handlers.interview import handle_text_message
            await handle_text_message(update, context)

        # The greeting message (id=2000) must be edited
        found = False
        for call in context.bot.edit_message_text.call_args_list:
            if call[1].get("message_id") == greeting_msg_id:
                found = True
                break
        assert found, (
            f"Greeting msg {greeting_msg_id} must be edited by first progress step"
        )
