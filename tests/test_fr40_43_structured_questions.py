"""Tests for FR-40..FR-48: structured questions, always-run clarification,
single-message editing, separate LLM calls, editable prompts/messages,
progress bar %, URL handling, and greeting overwrite."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tests.conftest import (
    BotMock,
    SAMPLE_ASIS_MODEL,
    SAMPLE_MERMAID,
    SAMPLE_NARRATIVE,
    SAMPLE_OPPORTUNITIES,
    SAMPLE_CLARIFICATION_QUESTIONS,
    SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
    make_bot_mock,
    make_update,
)
from bot.models import AsIsModel, InterviewSession, Process, RawInput
from bot.states import GapStatus, ProcessStatus, SessionStatus


# ============================================================================
# FR-40: Clarification always runs after extraction
# ============================================================================


class TestFR40_AlwaysClarification:
    """FR-40: Clarification Q&A always runs after extraction (no threshold gate)."""

    @pytest.mark.asyncio
    async def test_clarification_always_starts(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.1: _process_input always calls start_clarification_flow."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Полное описание процесса с ролями, системами, метриками.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.handlers.clarification.start_clarification_flow",
                new_callable=AsyncMock,
            ) as mock_clar,
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        mock_clar.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_gap_detector_in_main_flow(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.2: _process_input does NOT call detect_gaps."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Описание процесса.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.handlers.clarification.start_clarification_flow",
                new_callable=AsyncMock,
            ),
            patch(
                "bot.services.gap_detector.chat",
                new_callable=AsyncMock,
            ) as mock_gap,
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        # gap_detector should NOT be called
        mock_gap.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_set_to_clarification_status(
        self, db_session, patch_db, seed_process, seed_session, seed_asis_model
    ):
        """FR-40.3: Process status is set to CLARIFICATION_IN_PROGRESS."""
        raw = RawInput(
            session_id=seed_session.id,
            message_type="text",
            raw_text="Описание.",
        )
        db_session.add(raw)
        seed_session.state = SessionStatus.PROCESSING_INPUT
        seed_process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
        await db_session.commit()

        bot = make_bot_mock()

        with (
            patch(
                "bot.services.extractor.chat",
                new_callable=AsyncMock,
                return_value=json.dumps(SAMPLE_ASIS_MODEL, ensure_ascii=False),
            ),
            patch(
                "bot.handlers.clarification.start_clarification_flow",
                new_callable=AsyncMock,
            ),
        ):
            from bot.handlers.interview import _process_input

            await _process_input(bot, 99999, seed_process.id, seed_session.id)

        await db_session.refresh(seed_process)
        assert seed_process.status == ProcessStatus.CLARIFICATION_IN_PROGRESS


# ============================================================================
# FR-41: Questions only for empty fields per stage
# ============================================================================


class TestFR41_StructuredClarificationQuestions:
    """FR-41: Clarification questions must only target actually empty fields."""

    @pytest.mark.asyncio
    async def test_prompt_mentions_stage_fields(self):
        """FR-41.1: The clarification prompt checks per-stage fields."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")

        assert "owner_role" in prompt or "Роль" in prompt or "роли" in prompt.lower()
        assert "systems" in prompt or "Система" in prompt or "систем" in prompt.lower()
        assert "metrics" in prompt or "Метрик" in prompt or "метрик" in prompt.lower()
        assert "inputs" in prompt or "Артефакт" in prompt or "артефакт" in prompt.lower()
        assert "outputs" in prompt or "выход" in prompt or "выход" in prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_requires_empty_fields_only(self):
        """FR-41.2: Prompt instructs to ask ONLY about empty fields."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")

        assert "пуст" in prompt.lower() or "отсутств" in prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_has_max_5_questions(self):
        """FR-41.3: Max 5 questions."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")

        assert "5" in prompt

    @pytest.mark.asyncio
    async def test_prompts_loaded_from_files(self):
        """FR-41.4: All prompts are loaded from separate .txt files."""
        from bot.prompts import load_prompt

        for name in [
            "extractor", "gap_detector", "generator", "mermaid",
            "opportunities", "clarification_questions", "answer_extractor",
        ]:
            prompt = load_prompt(name)
            assert len(prompt) > 50, f"Prompt '{name}' should be non-trivial"


# ============================================================================
# FR-42: Question priority order
# ============================================================================


class TestFR42_QuestionPriority:
    """FR-42: Questions prioritized: operations > metrics > roles > systems > artifacts."""

    @pytest.mark.asyncio
    async def test_priority_order_in_prompt(self):
        """FR-42.1: Clarification prompt specifies the 5 categories in order."""
        from bot.prompts import load_prompt
        prompt = load_prompt("clarification_questions")

        # Find the numbered list items
        prompt_lower = prompt.lower()

        idx_ops = prompt_lower.find("операции") if prompt_lower.find("операции") >= 0 else prompt_lower.find("шаг")
        idx_metrics = prompt_lower.find("метрики")
        idx_roles = prompt_lower.find("роли")
        idx_systems = prompt_lower.find("системы")
        idx_artifacts = prompt_lower.find("артефакты")

        assert idx_ops > -1, "Operations mentioned in prompt"
        assert idx_metrics > -1, "Metrics mentioned in prompt"
        assert idx_roles > -1, "Roles mentioned in prompt"
        assert idx_systems > -1, "Systems mentioned in prompt"
        assert idx_artifacts > -1, "Artifacts mentioned in prompt"

        assert idx_ops < idx_metrics, "Operations must come before metrics"
        assert idx_metrics < idx_roles, "Metrics must come before roles"
        assert idx_roles < idx_systems, "Roles must come before systems"
        assert idx_systems < idx_artifacts, "Systems must come before artifacts"

    @pytest.mark.asyncio
    async def test_service_question_order_constant(self):
        """FR-42.2: QUESTION_ORDER constant matches expected order."""
        from bot.services.clarification import QUESTION_ORDER

        assert QUESTION_ORDER == ["operations", "metrics", "roles", "systems", "artifacts"]


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
    async def test_clarification_question_edits_progress_message(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-35.1: Clarification question replaces progress message via edit."""
        bot = make_bot_mock()
        progress_msg_id = 5000

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": progress_msg_id,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import _show_clarification_question

        await _show_clarification_question(99999, bot, progress_msg_id)

        bot.edit_message_text.assert_called()
        edit_kwargs = bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == progress_msg_id
        assert "Уточняющий вопрос" in edit_kwargs["text"]

    @pytest.mark.asyncio
    async def test_skip_edits_same_message(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-35.2: Skipping a question edits the same message to next question."""
        bot = make_bot_mock()
        msg_id = 6000

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": msg_id,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import handle_clarification_skip

        await handle_clarification_skip(99999, bot, msg_id)

        bot.edit_message_text.assert_called()
        edit_kwargs = bot.edit_message_text.call_args[1]
        assert edit_kwargs["message_id"] == msg_id

    @pytest.mark.asyncio
    async def test_no_new_messages_during_clarification_flow(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-35.5: During clarification flow, bot.send_message is NOT called."""
        bot = make_bot_mock()
        progress_msg_id = 9000

        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": progress_msg_id,
            "clarification_questions": SAMPLE_CLARIFICATION_QUESTIONS_INCLUDED,
            "clarification_index": 0,
            "clarification_active": True,
        })

        from bot.handlers.clarification import _show_clarification_question

        await _show_clarification_question(99999, bot, progress_msg_id)

        # send_message should NOT be called when progress_id is provided
        bot.send_message.assert_not_called()

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


# ============================================================================
# FR-36 (updated): User messages deleted, bot edits one message
# ============================================================================


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
                "bot.handlers.clarification.start_clarification_flow",
                new_callable=AsyncMock,
            ),
        ):
            from bot.handlers.interview import handle_text_message

            await handle_text_message(update, context)

        # User message must be deleted
        context.bot.delete_message.assert_any_call(chat_id=99999, message_id=42)

        # Bot should edit existing message (bot_message_id=3000), not send new
        found_edit = False
        for call in context.bot.edit_message_text.call_args_list:
            if call[1].get("message_id") == 3000:
                found_edit = True
                break
        assert found_edit, "Bot should edit existing message_id=3000"


# ============================================================================
# FR-44: Prompts in separate .txt files
# ============================================================================


class TestFR44_PromptsInFiles:
    """FR-44: All LLM prompts are loaded from bot/prompts/*.txt files."""

    @pytest.mark.asyncio
    async def test_all_prompt_files_exist(self):
        """FR-44.1: All prompt files exist and are non-trivial."""
        from bot.prompts import load_prompt

        for name in [
            "extractor", "gap_detector", "generator", "mermaid",
            "opportunities", "clarification_questions", "answer_extractor",
        ]:
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
        from bot.services.clarification import QUESTIONS_PROMPT as clar_prompt
        from bot.services.clarification import ANSWER_PROMPT as ans_prompt
        from bot.prompts import load_prompt

        assert ext_prompt == load_prompt("extractor")
        assert gap_prompt == load_prompt("gap_detector")
        assert gen_prompt == load_prompt("generator")
        assert merm_prompt == load_prompt("mermaid")
        assert opp_prompt == load_prompt("opportunities")
        assert clar_prompt == load_prompt("clarification_questions")
        assert ans_prompt == load_prompt("answer_extractor")


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
            # Clarification flow messages
            "CLARIFICATION_GENERATING", "CLARIFICATION_GENERATING_DETAIL",
            "CLARIFICATION_QUESTION_PREFIX",
            "CLARIFICATION_SUGGESTIONS",
            "CLARIFICATION_ANSWER_HINT",
            "CLARIFICATION_EXTRACTING", "CLARIFICATION_EXTRACTING_DETAIL",
            "CLARIFICATION_SKIPPED",
            "CLARIFICATION_DONE", "CLARIFICATION_DONE_DETAIL",
            "CLARIFICATION_NO_QUESTIONS",
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
        result = bmsg.ASIS_READY_TEXT.format(name="Test", url="https://example.com")
        assert "Test" in result
        assert "https://example.com" in result

    @pytest.mark.asyncio
    async def test_asis_ready_text_has_hyperlink(self):
        """FR-45.3: ASIS_READY_TEXT formats URL as Markdown hyperlink."""
        import bot.messages as bmsg

        result = bmsg.ASIS_READY_TEXT.format(name="Test", url="https://example.com")
        assert "[📄 Открыть AS-IS](https://example.com)" in result


# ============================================================================
# FR-46: Progress bar shows % towards HTML (6 steps)
# ============================================================================


class TestFR46_ProgressBarPercentage:
    """FR-46: Progress bar uses 6 total steps."""

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


# ============================================================================
# FR-48: Greeting message overwritten by first progress step
# ============================================================================


class TestFR48_GreetingOverwrite:
    """FR-48: Greeting is saved as bot_message_id and overwritten by progress."""

    @pytest.mark.asyncio
    async def test_new_process_greeting_saved_as_bot_message_id(
        self, db_session, patch_db, seed_company, seed_respondent
    ):
        """FR-48.1: handle_new_process_name stores greeting message_id in context."""
        bot = make_bot_mock()

        from bot.handlers.start import handle_new_process_name
        from bot.handlers.callbacks import save_chat_context, get_chat_context

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
        assert "bot_message_id" in ctx
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

        from bot.handlers.callbacks import save_chat_context
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
                "bot.handlers.clarification.start_clarification_flow",
                new_callable=AsyncMock,
            ),
        ):
            from bot.handlers.interview import handle_text_message
            await handle_text_message(update, context)

        found = False
        for call in context.bot.edit_message_text.call_args_list:
            if call[1].get("message_id") == greeting_msg_id:
                found = True
                break
        assert found, (
            f"Greeting msg {greeting_msg_id} must be edited by first progress step"
        )


# ============================================================================
# FR-49: Questions 2-5 generated after Q1 (operations)
# ============================================================================


class TestFR49_DynamicQuestionsAfterOperations:
    """FR-49: Questions 2–5 are regenerated after Q1 is answered/skipped."""

    @pytest.mark.asyncio
    async def test_only_operations_question_shown_initially(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-49.1: When operations question is included, only it is shown first."""
        bot = make_bot_mock()

        all_included = {
            "questions": [
                {"field_type": "operations", "include": True, "question": "Ops?", "suggestions": ["a"]},
                {"field_type": "metrics", "include": True, "question": "Met?", "suggestions": ["b"]},
                {"field_type": "roles", "include": True, "question": "Rol?", "suggestions": ["c"]},
                {"field_type": "systems", "include": True, "question": "Sys?", "suggestions": ["d"]},
                {"field_type": "artifacts", "include": True, "question": "Art?", "suggestions": ["e"]},
            ]
        }

        from bot.handlers.callbacks import save_chat_context, get_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
        })

        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(all_included, ensure_ascii=False),
        ):
            from bot.handlers.clarification import start_clarification_flow

            await start_clarification_flow(99999, seed_process.id, bot, 5000)

        ctx = await get_chat_context(99999)
        # Only 1 question should be stored initially (operations only)
        assert len(ctx["clarification_questions"]) == 1
        assert ctx["clarification_questions"][0]["field_type"] == "operations"

    @pytest.mark.asyncio
    async def test_skip_operations_regenerates_remaining(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-49.2: Skipping operations regenerates remaining questions."""
        bot = make_bot_mock()

        from bot.handlers.callbacks import save_chat_context, get_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
            "clarification_questions": [
                {"field_type": "operations", "question": "Ops?", "suggestions": ["a"]},
            ],
            "clarification_index": 0,
            "clarification_active": True,
        })

        regenerated = {
            "questions": [
                {"field_type": "operations", "include": False, "question": "", "suggestions": []},
                {"field_type": "metrics", "include": True, "question": "New metrics?", "suggestions": ["x"]},
                {"field_type": "roles", "include": False, "question": "", "suggestions": []},
                {"field_type": "systems", "include": True, "question": "New sys?", "suggestions": ["y"]},
                {"field_type": "artifacts", "include": False, "question": "", "suggestions": []},
            ]
        }

        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(regenerated, ensure_ascii=False),
        ):
            from bot.handlers.clarification import handle_clarification_skip

            await handle_clarification_skip(99999, bot, 5000)

        ctx = await get_chat_context(99999)
        # Should have ops + 2 regenerated questions = 3 total
        assert len(ctx["clarification_questions"]) == 3
        assert ctx["clarification_index"] == 1
        assert ctx["clarification_questions"][1]["field_type"] == "metrics"
        assert ctx["clarification_questions"][2]["field_type"] == "systems"

    @pytest.mark.asyncio
    async def test_non_operations_questions_not_deferred(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-49.3: When no operations question, all questions shown at once."""
        bot = make_bot_mock()

        no_ops = {
            "questions": [
                {"field_type": "operations", "include": False, "question": "", "suggestions": []},
                {"field_type": "metrics", "include": True, "question": "Met?", "suggestions": ["b"]},
                {"field_type": "roles", "include": True, "question": "Rol?", "suggestions": ["c"]},
                {"field_type": "systems", "include": False, "question": "", "suggestions": []},
                {"field_type": "artifacts", "include": True, "question": "Art?", "suggestions": ["e"]},
            ]
        }

        from bot.handlers.callbacks import save_chat_context, get_chat_context
        await save_chat_context(99999, {
            "session_id": 1,
            "process_id": seed_process.id,
            "bot_message_id": 5000,
        })

        with patch(
            "bot.services.clarification.chat",
            new_callable=AsyncMock,
            return_value=json.dumps(no_ops, ensure_ascii=False),
        ):
            from bot.handlers.clarification import start_clarification_flow

            await start_clarification_flow(99999, seed_process.id, bot, 5000)

        ctx = await get_chat_context(99999)
        # All 3 questions should be stored (no deferral)
        assert len(ctx["clarification_questions"]) == 3


# ============================================================================
# FR-50: No question numbers shown
# ============================================================================


class TestFR50_NoQuestionNumbers:
    """FR-50: Question numbers are not shown to the user."""

    @pytest.mark.asyncio
    async def test_question_prefix_has_no_numbers(self):
        """FR-50.1: CLARIFICATION_QUESTION_PREFIX has no {num} or {total}."""
        import bot.messages as bmsg

        assert "{num}" not in bmsg.CLARIFICATION_QUESTION_PREFIX
        assert "{total}" not in bmsg.CLARIFICATION_QUESTION_PREFIX

    @pytest.mark.asyncio
    async def test_question_text_has_no_number_prefix(
        self, db_session, patch_db, seed_process, seed_asis_model,
    ):
        """FR-50.2: Displayed question text does not contain 'N из M'."""
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
        # Should not contain number patterns
        assert " из " not in text
        assert "Уточняющий вопрос" in text


# ============================================================================
# FR-51: HTML-to-PDF generation
# ============================================================================


class TestFR51_PdfGeneration:
    """FR-51: HTML page is converted to PDF via WeasyPrint."""

    @pytest.mark.asyncio
    async def test_pdf_converter_service_exists(self):
        """FR-51.1: PDF converter service module exists."""
        from bot.services.pdf_converter import convert_html_to_pdf

        assert callable(convert_html_to_pdf)

    @pytest.mark.asyncio
    async def test_pdf_converter_returns_none_for_missing_html(self, tmp_path):
        """FR-51.2: Returns None when HTML file does not exist."""
        with patch("bot.services.pdf_converter.PAGES_DIR", tmp_path):
            from bot.services.pdf_converter import convert_html_to_pdf

            result = await convert_html_to_pdf("nonexistent_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_published_page_has_pdf_path_column(self):
        """FR-51.3: PublishedPage model has pdf_path column."""
        from bot.models import PublishedPage

        assert hasattr(PublishedPage, "pdf_path")

    @pytest.mark.asyncio
    async def test_weasyprint_in_requirements(self):
        """FR-51.4: weasyprint is listed in requirements.txt."""
        from pathlib import Path

        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        assert "weasyprint" in content.lower()


# ============================================================================
# FR-52: Stage blocks with big headers, spacing, per-operation metrics
# ============================================================================


class TestFR52_StageBlockStyling:
    """FR-52: Stages section has big headers, spacing, per-operation metrics."""

    @pytest.mark.asyncio
    async def test_template_has_stage_block_css(self):
        """FR-52.1: HTML template defines .stage-block CSS class."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "bot" / "templates" / "asis_page.html"
        content = template_path.read_text()
        assert ".stage-block" in content
        assert ".stage-title" in content
        assert ".stage-details" in content

    @pytest.mark.asyncio
    async def test_stage_block_has_margin(self):
        """FR-52.2: .stage-block has margin-bottom for spacing."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "bot" / "templates" / "asis_page.html"
        content = template_path.read_text()
        assert "margin-bottom: 2rem" in content

    @pytest.mark.asyncio
    async def test_stage_title_is_large(self):
        """FR-52.3: .stage-title has a large font size."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent / "bot" / "templates" / "asis_page.html"
        content = template_path.read_text()
        assert "font-size: 1.25rem" in content

    @pytest.mark.asyncio
    async def test_generator_prompt_mentions_stage_metrics(self):
        """FR-52.4: Generator prompt instructs per-operation metrics."""
        from bot.prompts import load_prompt

        prompt = load_prompt("generator")
        assert "Метрики" in prompt
        assert "stage-block" in prompt
        assert "stage-title" in prompt
