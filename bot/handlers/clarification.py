"""Follow-up question flow and AS-IS generation trigger with progress UX."""

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
)
from bot.services.generator import generate_narrative
from bot.services.mermaid import generate_mermaid
from bot.services.opportunities import generate_opportunities
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

        from bot.models import RawInput

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
    async with async_session() as db:
        page = PublishedPage(process_id=process_id, mermaid_code=mermaid_code)
        db.add(page)
        await db.flush()

        url = await publish_page(page.token, narrative, mermaid_code)
        if url:
            page.html_url = url
            page.narrative_html = json.dumps(narrative, ensure_ascii=False)

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
    """Edit the progress message into the final result with AS-IS link."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    if url:
        # Build keyboard — only use url= button if URL is https
        buttons = []
        if url.startswith("https://"):
            buttons.append([InlineKeyboardButton(msg.BTN_OPEN_ASIS, url=url)])
        if opps:
            buttons.append([
                InlineKeyboardButton(
                    msg.BTN_CONTINUE_OPPS,
                    callback_data=f"start_opps_{process_id}",
                )
            ])
        keyboard = InlineKeyboardMarkup(buttons) if buttons else None

        text = msg.ASIS_READY_TEXT.format(name=process_name, url=url)
    else:
        keyboard = None
        if opps:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    msg.BTN_CONTINUE_OPPS,
                    callback_data=f"start_opps_{process_id}",
                )
            ]])
        text = msg.ASIS_READY_TEXT_NO_URL.format(name=process_name)

    if not opps:
        text += f"\n\n{msg.GEN_NO_OPPS}"

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
            logger.debug("Could not edit progress message, sending new")

    if sent_id is None:
        result = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        sent_id = result.message_id

    ctx = await get_chat_context(chat_id) or {}
    ctx["bot_message_id"] = sent_id
    await save_chat_context(chat_id, ctx)


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
