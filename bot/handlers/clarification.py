"""Clarification Q&A flow and AS-IS generation trigger with progress UX.

New flow: after initial extraction, LLM generates up to 5 structured questions
(operations, metrics, roles, systems, artifacts). Each question is shown with
only a "Skip" button. User answers directly via text/voice. LLM extracts
answers and updates the AS-IS model.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.handlers.progress import delete_messages, send_progress, send_step
from bot.models import (
    AsIsModel,
    AutomationOpportunity,
    Gap,
    Process,
    PublishedPage,
    InterviewSession,
    RawInput,
)
from bot.services.clarification import (
    extract_answer,
    generate_clarification_questions,
    merge_extracted_answer,
)
from bot.services.generator import generate_narrative
from bot.services.mermaid import generate_mermaid
from bot.services.opportunities import generate_opportunities
from bot.services.pdf_converter import convert_html_to_pdf
from bot.services.publisher import publish_page
from bot.states import (
    GapStatus,
    OpportunityStatus,
    OpportunityType,
    ProcessStatus,
    SessionStatus,
)
import bot.messages as msg

logger = logging.getLogger(__name__)

# Same total as interview.py — progress bar is continuous
TOTAL_STEPS = 6


async def start_clarification_flow(
    chat_id: int, process_id: int, bot,
    progress_id: int | None = None,
) -> None:
    """Generate clarification questions and start the sequential Q&A.

    Called after initial extraction. Always runs — LLM decides which
    questions to include (operations, metrics, roles, systems, artifacts).
    If no questions needed, proceeds directly to AS-IS generation.
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    # Show progress: generating questions
    progress_id = await send_step(
        bot, chat_id, 3, TOTAL_STEPS,
        msg.CLARIFICATION_GENERATING, msg.CLARIFICATION_GENERATING_DETAIL,
        progress_id,
    )

    # Load AS-IS model
    async with async_session() as db:
        process = await db.get(Process, process_id)
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()

        if not asis or not process:
            await send_progress(bot, chat_id, msg.GEN_NO_DATA, progress_id)
            return

        model_data = _model_to_dict(asis)

    # LLM: generate clarification questions
    questions = await generate_clarification_questions(process.name, model_data)

    if not questions:
        # No questions needed — proceed to generation
        await send_progress(
            bot, chat_id, msg.CLARIFICATION_NO_QUESTIONS, progress_id,
        )
        await trigger_asis_generation(chat_id, process_id, bot, progress_id)
        return

    # If the first question is about operations, show ONLY it for now.
    # Questions 2–5 will be regenerated after Q1 is answered/skipped
    # (because the user may add new stages, changing what needs clarifying).
    has_ops_first = questions[0].get("field_type") == "operations"
    initial_questions = [questions[0]] if has_ops_first else questions

    # Store questions in chat context
    ctx = await get_chat_context(chat_id) or {}
    ctx["clarification_questions"] = initial_questions
    ctx["clarification_index"] = 0
    ctx["clarification_active"] = True
    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    # Show first question
    await _show_clarification_question(chat_id, bot, progress_id)


async def _show_clarification_question(
    chat_id: int, bot, progress_id: int | None = None,
) -> None:
    """Show the current clarification question with Skip button."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    ctx = await get_chat_context(chat_id) or {}
    questions = ctx.get("clarification_questions", [])
    index = ctx.get("clarification_index", 0)

    if index >= len(questions):
        # All questions done
        await _finish_clarification(chat_id, bot, progress_id)
        return

    q = questions[index]

    # Build question text
    text = msg.CLARIFICATION_QUESTION_PREFIX
    text += f"\n\n{q['question']}"

    # Add suggestions
    if q.get("suggestions"):
        suggestions_text = "\n".join(f"• {s}" for s in q["suggestions"])
        text += msg.CLARIFICATION_SUGGESTIONS.format(suggestions=suggestions_text)

    text += msg.CLARIFICATION_ANSWER_HINT

    # Only one button: Skip
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(msg.BTN_SKIP, callback_data="skip_clarification")]
    ])

    sent_id = None
    if progress_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            sent_id = progress_id
        except Exception:
            pass

    if sent_id is None:
        result = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        sent_id = result.message_id

    ctx["bot_message_id"] = sent_id
    await save_chat_context(chat_id, ctx)


async def handle_clarification_answer(
    update: Update, answer_text: str,
) -> None:
    """Process user's text/voice answer to the current clarification question.

    Extracts structured data via LLM and merges into AS-IS model.
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    chat_id = update.effective_chat.id
    bot = update.get_bot()

    # Delete user's message
    if update.message:
        await delete_messages(bot, chat_id, [update.message.message_id])

    ctx = await get_chat_context(chat_id) or {}
    questions = ctx.get("clarification_questions", [])
    index = ctx.get("clarification_index", 0)
    process_id = ctx.get("process_id")
    progress_id = ctx.get("bot_message_id")

    if index >= len(questions) or not process_id:
        return

    q = questions[index]

    # Show extracting progress
    progress_id = await send_step(
        bot, chat_id, 3, TOTAL_STEPS,
        msg.CLARIFICATION_EXTRACTING, msg.CLARIFICATION_EXTRACTING_DETAIL,
        progress_id,
    )

    # Save raw input
    async with async_session() as db:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.process_id == process_id,
                InterviewSession.state != SessionStatus.COMPLETED,
            ).limit(1)
        )
        session = result.scalar_one_or_none()
        if session:
            raw = RawInput(
                session_id=session.id,
                message_type="text",
                raw_text=answer_text,
                telegram_message_id=(
                    update.message.message_id if update.message else None
                ),
            )
            db.add(raw)
            await db.commit()

    # Load current AS-IS model
    async with async_session() as db:
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        if not asis:
            return

        process = await db.get(Process, process_id)
        model_data = _model_to_dict(asis)

    # LLM: extract answer
    extracted = await extract_answer(
        q["field_type"], q["question"], answer_text, model_data,
    )

    # Merge into model
    updated_model = merge_extracted_answer(model_data, q["field_type"], extracted)

    # Save updated model
    async with async_session() as db:
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        if asis:
            asis.goal = updated_model.get("goal")
            asis.summary = updated_model.get("summary")
            asis.stages = json.dumps(updated_model.get("stages", []), ensure_ascii=False)
            asis.roles = json.dumps(updated_model.get("roles", []), ensure_ascii=False)
            asis.systems = json.dumps(updated_model.get("systems", []), ensure_ascii=False)
            asis.artifacts = json.dumps(updated_model.get("artifacts", []), ensure_ascii=False)
            asis.metrics = json.dumps(updated_model.get("metrics", []), ensure_ascii=False)
            asis.triggers = json.dumps(updated_model.get("triggers", []), ensure_ascii=False)
            asis.inputs = json.dumps(updated_model.get("inputs", []), ensure_ascii=False)
            asis.outputs = json.dumps(updated_model.get("outputs", []), ensure_ascii=False)
            asis.pain_points = json.dumps(updated_model.get("pain_points", []), ensure_ascii=False)
            asis.handoffs = json.dumps(updated_model.get("handoffs", []), ensure_ascii=False)
            asis.version += 1
            await db.commit()

    # If the user just answered the "operations" question, regenerate
    # remaining questions (2–5) because new stages may have been added.
    if q["field_type"] == "operations":
        remaining = await _regenerate_remaining_questions(
            process_id, process.name if process else "", updated_model,
        )
        ctx["clarification_questions"] = [q] + remaining
        ctx["clarification_index"] = 1
    else:
        ctx["clarification_index"] = index + 1

    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    await _show_clarification_question(chat_id, bot, progress_id)


async def handle_clarification_skip(
    chat_id: int, bot, message_id: int | None = None,
) -> None:
    """Skip current clarification question and show the next one."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    ctx = await get_chat_context(chat_id) or {}
    questions = ctx.get("clarification_questions", [])
    index = ctx.get("clarification_index", 0)
    process_id = ctx.get("process_id")

    current_q = questions[index] if index < len(questions) else None

    # If skipping the operations question, regenerate remaining questions
    # based on the current (unchanged) model.
    if current_q and current_q.get("field_type") == "operations" and process_id:
        async with async_session() as db:
            result = await db.execute(
                select(AsIsModel).where(AsIsModel.process_id == process_id)
            )
            asis = result.scalar_one_or_none()
            process = await db.get(Process, process_id)
            if asis and process:
                model_data = _model_to_dict(asis)
                remaining = await _regenerate_remaining_questions(
                    process_id, process.name, model_data,
                )
                ctx["clarification_questions"] = [current_q] + remaining
                ctx["clarification_index"] = 1
                await save_chat_context(chat_id, ctx)
                await _show_clarification_question(chat_id, bot, message_id)
                return

    ctx["clarification_index"] = index + 1
    await save_chat_context(chat_id, ctx)

    await _show_clarification_question(chat_id, bot, message_id)


async def _finish_clarification(
    chat_id: int, bot, progress_id: int | None = None,
) -> None:
    """All clarification questions answered/skipped. Trigger AS-IS generation."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    ctx = await get_chat_context(chat_id) or {}
    process_id = ctx.get("process_id")

    # Clear clarification state
    ctx.pop("clarification_questions", None)
    ctx.pop("clarification_index", None)
    ctx["clarification_active"] = False
    await save_chat_context(chat_id, ctx)

    if not process_id:
        return

    # Mark session completed and process ready
    async with async_session() as db:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.process_id == process_id,
                InterviewSession.state != SessionStatus.COMPLETED,
            ).limit(1)
        )
        session = result.scalar_one_or_none()
        if session:
            session.state = SessionStatus.COMPLETED

        process = await db.get(Process, process_id)
        if process:
            process.status = ProcessStatus.ASIS_READY
        await db.commit()

    progress_id = await send_step(
        bot, chat_id, 3, TOTAL_STEPS,
        msg.CLARIFICATION_DONE, msg.CLARIFICATION_DONE_DETAIL,
        progress_id,
    )

    await trigger_asis_generation(chat_id, process_id, bot, progress_id)


# ---------------------------------------------------------------------------
# Legacy gap-based flow (kept for backward compatibility)
# ---------------------------------------------------------------------------

async def send_next_gap_question(
    chat_id: int, process_id: int, update_or_bot,
    progress_id: int | None = None,
) -> None:
    """Send the next pending gap question with inline buttons.

    Edits the existing progress_id message into the question.
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    async with async_session() as db:
        result = await db.execute(
            select(Gap)
            .where(Gap.process_id == process_id, Gap.status == GapStatus.PENDING)
            .order_by(Gap.confidence_score.asc())
            .limit(1)
        )
        gap = result.scalar_one_or_none()

    if gap is None:
        # No more gaps → trigger AS-IS generation
        await trigger_asis_generation(
            chat_id, process_id, update_or_bot, progress_id,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(msg.BTN_ANSWER, callback_data=f"answer_{gap.id}"),
                InlineKeyboardButton(msg.BTN_SKIP, callback_data=f"skip_{gap.id}"),
            ],
            [
                InlineKeyboardButton(
                    msg.BTN_PAUSE, callback_data=f"pause_{process_id}"
                )
            ],
        ]
    )

    bot = _get_bot(update_or_bot)
    text = f"❓ {gap.question_text}"

    sent_id = None
    if progress_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=text,
                reply_markup=keyboard,
            )
            sent_id = progress_id
        except Exception:
            pass

    if sent_id is None:
        result = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
        )
        sent_id = result.message_id

    # Store the bot message id so future edits go to the same message
    ctx = await get_chat_context(chat_id) or {}
    ctx["bot_message_id"] = sent_id
    await save_chat_context(chat_id, ctx)


async def handle_gap_answer(
    update: Update, gap_id: int, answer_text: str
) -> None:
    """Process answer to a gap question."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    chat_id = update.effective_chat.id
    bot = update.get_bot()

    # Delete user's answer message
    if update.message:
        await delete_messages(bot, chat_id, [update.message.message_id])

    # Get the bot message to reuse for progress
    ctx = await get_chat_context(chat_id) or {}
    progress_id = ctx.get("bot_message_id")

    async with async_session() as db:
        gap = await db.get(Gap, gap_id)
        if not gap:
            return

        gap.status = GapStatus.ANSWERED
        process_id = gap.process_id

        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.process_id == process_id,
                InterviewSession.state != SessionStatus.COMPLETED,
            )
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session:
            raw = RawInput(
                session_id=session.id,
                message_type="text",
                raw_text=answer_text,
                telegram_message_id=(
                    update.message.message_id if update.message else None
                ),
            )
            db.add(raw)
            gap.answer_ref = raw.id

        await db.commit()

    # Edit the existing bot message to show progress
    progress_id = await send_step(
        bot, chat_id, 1, TOTAL_STEPS,
        msg.GAP_ANSWER_SAVED, msg.GAP_ANSWER_SAVED_DETAIL,
        progress_id,
    )

    # Store updated bot message id
    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    from bot.handlers.interview import _process_input
    if session:
        await _process_input(bot, chat_id, process_id, session.id, progress_id)


async def handle_gap_skip(
    chat_id: int, gap_id: int, update_or_bot,
    message_id: int | None = None,
) -> None:
    """Mark a gap as skipped and edit the same message to next question."""
    async with async_session() as db:
        gap = await db.get(Gap, gap_id)
        if not gap:
            return
        gap.status = GapStatus.SKIPPED
        process_id = gap.process_id
        await db.commit()

    bot = _get_bot(update_or_bot)

    # Edit the same message to show next question
    await send_next_gap_question(chat_id, process_id, update_or_bot, message_id)


async def handle_pause(chat_id: int, process_id: int, update_or_bot) -> None:
    """Pause the interview session."""
    from bot.handlers.callbacks import get_chat_context

    async with async_session() as db:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.process_id == process_id,
                InterviewSession.state != SessionStatus.COMPLETED,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.state = SessionStatus.PAUSED
            await db.commit()

    bot = _get_bot(update_or_bot)

    # Edit existing bot message instead of sending new
    ctx = await get_chat_context(chat_id) or {}
    progress_id = ctx.get("bot_message_id")

    if progress_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_id,
                text=msg.SESSION_PAUSED,
            )
            return
        except Exception:
            pass

    await bot.send_message(chat_id=chat_id, text=msg.SESSION_PAUSED)


async def trigger_asis_generation(
    chat_id: int, process_id: int, update_or_bot,
    progress_id: int | None = None,
) -> None:
    """Generate AS-IS page: narrative + mermaid + HTML with step-by-step progress.

    All progress is shown by editing a single message. At the end the message
    becomes a link to the published AS-IS page.
    Progress steps 4, 5, 6 of TOTAL_STEPS(6).
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    bot = _get_bot(update_or_bot)

    async with async_session() as db:
        process = await db.get(Process, process_id)
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()

        if not asis or not process:
            await send_progress(bot, chat_id, msg.GEN_NO_DATA, progress_id)
            return

        model_data = _model_to_dict(asis)

    # LLM Call 3: Generate narrative  (step 4 of 6)
    progress_id = await send_step(
        bot, chat_id, 4, TOTAL_STEPS,
        msg.GEN_NARRATIVE, msg.GEN_NARRATIVE_DETAIL,
        progress_id,
    )
    narrative = await generate_narrative(process.name, model_data)

    # LLM Call 4: Generate Mermaid diagram  (step 5 of 6)
    progress_id = await send_step(
        bot, chat_id, 5, TOTAL_STEPS,
        msg.GEN_DIAGRAM, msg.GEN_DIAGRAM_DETAIL,
        progress_id,
    )
    mermaid_code = await generate_mermaid(process.name, model_data)

    # Publish HTML page  (step 6 of 6)
    progress_id = await send_step(
        bot, chat_id, 6, TOTAL_STEPS,
        msg.GEN_PUBLISH, msg.GEN_PUBLISH_DETAIL,
        progress_id,
    )

    url = None
    page_token = None
    async with async_session() as db:
        page = PublishedPage(process_id=process_id, mermaid_code=mermaid_code)
        db.add(page)
        await db.flush()
        page_token = page.token

        url = await publish_page(page.token, narrative, mermaid_code)
        if url:
            page.html_url = url
            page.narrative_html = json.dumps(narrative, ensure_ascii=False)

            # Generate PDF from the published HTML
            pdf_path = await convert_html_to_pdf(page.token)
            if pdf_path:
                page.pdf_path = pdf_path

            process = await db.get(Process, process_id)
            process.status = ProcessStatus.ASIS_PUBLISHED
        else:
            await send_progress(bot, chat_id, msg.GEN_PUBLISH_FAILED, progress_id)

        await db.commit()

    # LLM Call 5: Generate opportunities (runs after publish, no extra step in bar)
    opps = await _generate_opportunities_data(process_id, process.name)

    # Save opportunities
    async with async_session() as db:
        process = await db.get(Process, process_id)

        if opps:
            process.status = ProcessStatus.AUTOMATION_SELECTION_IN_PROGRESS

            for opp_data in opps:
                opp_type = None
                try:
                    opp_type = OpportunityType(opp_data.get("type", ""))
                except ValueError:
                    pass

                opp = AutomationOpportunity(
                    process_id=process_id,
                    stage_id=opp_data.get("stage_id"),
                    title=opp_data.get("title", ""),
                    opp_type=opp_type,
                    problem=opp_data.get("problem"),
                    description=opp_data.get("description"),
                    expected_benefit=opp_data.get("expected_benefit"),
                    status=OpportunityStatus.PROPOSED,
                )
                db.add(opp)

        await db.commit()

    # Edit progress message into final result with AS-IS link
    await _show_final_result(
        bot, chat_id, process_id, process.name, url, opps, progress_id,
    )


async def _generate_opportunities_data(
    process_id: int, process_name: str,
) -> list[dict]:
    """Run LLM to get opportunity data."""
    async with async_session() as db:
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        if not asis:
            return []
        model_data = _model_to_dict(asis)

    return await generate_opportunities(process_name, model_data)


async def _show_final_result(
    bot, chat_id: int, process_id: int, process_name: str,
    url: str | None, opps: list[dict],
    progress_id: int | None,
) -> None:
    """Delete the progress message and show opportunities inline."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context
    from bot.handlers.opportunities import show_opportunities_multiselect

    # Delete progress message (100% bar) — fresh message for opportunities
    if progress_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=progress_id)
        except Exception:
            pass

    ctx = await get_chat_context(chat_id) or {}
    ctx["clarification_active"] = False
    await save_chat_context(chat_id, ctx)

    if opps:
        # Show opportunities multiselect directly (with AS-IS link)
        await show_opportunities_multiselect(
            chat_id, process_id, bot, asis_url=url,
        )
    else:
        # No opportunities found — show AS-IS link only
        if url:
            text = msg.ASIS_READY_TEXT.format(name=process_name, url=url)
            text += f"\n\n{msg.GEN_NO_OPPS}"
            buttons = []
            if url.startswith("https://"):
                buttons.append([InlineKeyboardButton(msg.BTN_OPEN_ASIS, url=url)])
            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        else:
            text = msg.ASIS_READY_TEXT_NO_URL.format(name=process_name)
            text += f"\n\n{msg.GEN_NO_OPPS}"
            keyboard = None

        result = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        ctx["bot_message_id"] = result.message_id
        await save_chat_context(chat_id, ctx)


async def _regenerate_remaining_questions(
    process_id: int, process_name: str, updated_model: dict,
) -> list[dict]:
    """Re-generate questions 2–5 (metrics, roles, systems, artifacts) after
    the operations question has been answered, because new stages may have
    been added and the remaining questions need to account for them."""
    questions = await generate_clarification_questions(process_name, updated_model)
    # Keep only non-operations questions (operations was already answered)
    return [q for q in questions if q.get("field_type") != "operations"]


def _model_to_dict(m: AsIsModel) -> dict:
    """Convert ORM model to dict."""
    def _load(val):
        if val is None:
            return []
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "goal": m.goal,
        "summary": m.summary,
        "triggers": _load(m.triggers),
        "inputs": _load(m.inputs),
        "outputs": _load(m.outputs),
        "stages": _load(m.stages),
        "roles": _load(m.roles),
        "systems": _load(m.systems),
        "artifacts": _load(m.artifacts),
        "metrics": _load(m.metrics),
        "pain_points": _load(m.pain_points),
        "handoffs": _load(m.handoffs),
    }


def _get_bot(update_or_bot):
    """Extract bot instance from Update or return bot directly."""
    if isinstance(update_or_bot, Update):
        return update_or_bot.get_bot()
    # If it already has send_message, it's a bot
    if hasattr(update_or_bot, "send_message"):
        return update_or_bot
    # ContextTypes.DEFAULT_TYPE has .bot
    if hasattr(update_or_bot, "bot"):
        return update_or_bot.bot
    return update_or_bot
