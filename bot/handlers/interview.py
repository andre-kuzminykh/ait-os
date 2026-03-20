"""Interview flow handlers — process text/voice input with progress UX."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.handlers.progress import delete_messages, send_progress, send_step, typewriter_send
from bot.models import AsIsModel, InterviewSession, Process, RawInput
from bot.services.extractor import extract_asis_model
from bot.services.transcription import transcribe_telegram_voice
from bot.states import ProcessStatus, SessionStatus
import bot.messages as msg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Total steps in the whole pipeline: interview(2) + clarification(1) + generation(3) = 6
# The progress bar always shows step/TOTAL_STEPS.
# ---------------------------------------------------------------------------
TOTAL_STEPS = 6


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle plain text messages during interview."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)
    if not ctx:
        await update.message.reply_text(msg.NO_CONTEXT, parse_mode="Markdown")
        return

    session_id = ctx["session_id"]
    process_id = ctx["process_id"]

    text = update.message.text
    if not text or not text.strip():
        return

    bot = context.bot
    user_msg_id = update.message.message_id

    # Use the single bot message if stored in context
    progress_id = ctx.get("bot_message_id")

    async with async_session() as db:
        session = await db.get(InterviewSession, session_id)
        if not session:
            return

        raw = RawInput(
            session_id=session.id,
            message_type="text",
            telegram_message_id=update.message.message_id,
            raw_text=text,
        )
        db.add(raw)
        session.state = SessionStatus.PROCESSING_INPUT
        await db.commit()

    # Delete user's message, edit bot's message for progress
    await delete_messages(bot, chat_id, [user_msg_id])

    progress_id = await send_step(
        bot, chat_id, 1, TOTAL_STEPS,
        msg.INPUT_SAVED, msg.INPUT_SAVED_DETAIL,
        progress_id,
    )

    # Store the bot message id in context
    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    await _process_input(bot, chat_id, process_id, session_id, progress_id)


async def handle_voice_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle voice notes and audio files."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)
    if not ctx:
        return

    session_id = ctx["session_id"]
    process_id = ctx["process_id"]

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    bot = context.bot
    user_msg_id = update.message.message_id

    # Use the single bot message if stored in context
    progress_id = ctx.get("bot_message_id")

    # Delete user message, show progress in bot message
    await delete_messages(bot, chat_id, [user_msg_id])

    progress_id = await send_step(
        bot, chat_id, 1, TOTAL_STEPS,
        msg.VOICE_RECEIVED, msg.VOICE_RECEIVED_DETAIL,
        progress_id,
    )

    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    transcript = await transcribe_telegram_voice(bot, voice.file_id)

    if not transcript:
        await send_progress(bot, chat_id, msg.VOICE_FAILED, progress_id)
        return

    # Typewriter reveal of transcription
    progress_id = await send_step(
        bot, chat_id, 1, TOTAL_STEPS,
        msg.VOICE_TRANSCRIBING, msg.VOICE_TRANSCRIBING_DETAIL,
        progress_id,
    )
    progress_id = await typewriter_send(
        bot, chat_id, transcript,
        prefix=msg.VOICE_TRANSCRIPT_PREFIX, message_id=progress_id,
    )

    async with async_session() as db:
        session = await db.get(InterviewSession, session_id)
        if not session:
            return

        raw = RawInput(
            session_id=session.id,
            message_type="voice",
            telegram_message_id=update.message.message_id,
            file_ref=voice.file_id,
            transcript_text=transcript,
            raw_text=transcript,
        )
        db.add(raw)
        session.state = SessionStatus.PROCESSING_INPUT
        await db.commit()

    # Continue to analysis
    progress_id = await send_step(
        bot, chat_id, 1, TOTAL_STEPS,
        msg.ANALYZING, msg.ANALYZING_DETAIL,
        progress_id,
    )
    await _process_input(bot, chat_id, process_id, session_id, progress_id)


async def handle_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle audio file uploads."""
    from bot.handlers.callbacks import get_chat_context

    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)
    if not ctx:
        return

    doc = update.message.document
    if not doc:
        return

    mime = doc.mime_type or ""
    if not mime.startswith("audio/"):
        await update.message.reply_text(msg.AUDIO_ONLY)
        return

    # Treat as voice
    update.message.audio = doc  # duck-type for transcription
    await handle_voice_message(update, context)


async def _process_input(
    bot, chat_id: int, process_id: int, session_id: int,
    progress_id: int | None = None,
) -> None:
    """Extract AS-IS model, then always start clarification Q&A.

    Shows step-by-step progress by editing a single message.
    Progress bar goes from step 1..TOTAL_STEPS (6) where:
      step 1 = input saved
      step 2 = extracting structure
      step 3 = clarification questions
      step 4..6 = generation (handled in clarification.py)
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    async with async_session() as db:
        process = await db.get(Process, process_id)
        session = await db.get(InterviewSession, session_id)
        if not process or not session:
            return

        # Collect all raw texts for this process
        result = await db.execute(
            select(RawInput)
            .join(InterviewSession)
            .where(InterviewSession.process_id == process_id)
            .order_by(RawInput.created_at)
        )
        raw_inputs = result.scalars().all()
        raw_texts = [
            r.raw_text or r.transcript_text
            for r in raw_inputs
            if r.raw_text or r.transcript_text
        ]

        if not raw_texts:
            return

        # Get existing model
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        existing = result.scalar_one_or_none()
        existing_json = None
        if existing:
            existing_json = json.dumps(
                _model_to_dict(existing), ensure_ascii=False
            )

    # LLM Call 1: Extract/update AS-IS model  (step 2 of 6)
    progress_id = await send_step(
        bot, chat_id, 2, TOTAL_STEPS,
        msg.EXTRACTING_STRUCTURE, msg.EXTRACTING_STRUCTURE_DETAIL,
        progress_id,
    )

    model_data = await extract_asis_model(
        process.name, raw_texts, existing_json
    )

    if not model_data:
        await send_progress(bot, chat_id, msg.ANALYSIS_FAILED, progress_id)
        return

    # Save/update AS-IS model
    async with async_session() as db:
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        if asis is None:
            asis = AsIsModel(process_id=process_id)
            db.add(asis)
        else:
            asis.version += 1

        asis.goal = model_data.get("goal")
        asis.summary = model_data.get("summary")
        asis.triggers = json.dumps(model_data.get("triggers", []), ensure_ascii=False)
        asis.inputs = json.dumps(model_data.get("inputs", []), ensure_ascii=False)
        asis.outputs = json.dumps(model_data.get("outputs", []), ensure_ascii=False)
        asis.stages = json.dumps(model_data.get("stages", []), ensure_ascii=False)
        asis.roles = json.dumps(model_data.get("roles", []), ensure_ascii=False)
        asis.systems = json.dumps(model_data.get("systems", []), ensure_ascii=False)
        asis.artifacts = json.dumps(model_data.get("artifacts", []), ensure_ascii=False)
        asis.metrics = json.dumps(model_data.get("metrics", []), ensure_ascii=False)
        asis.pain_points = json.dumps(model_data.get("pain_points", []), ensure_ascii=False)
        asis.handoffs = json.dumps(model_data.get("handoffs", []), ensure_ascii=False)

        process = await db.get(Process, process_id)
        session = await db.get(InterviewSession, session_id)

        # Always go to clarification — LLM decides which questions to ask
        process.status = ProcessStatus.CLARIFICATION_IN_PROGRESS
        session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
        await db.commit()

    # Store bot_message_id so clarification edits the same message
    ctx = await get_chat_context(chat_id) or {}
    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    # Start 5-question clarification flow (step 3 of 6)
    # LLM generates questions; if none needed, proceeds directly to generation
    from bot.handlers.clarification import start_clarification_flow
    await start_clarification_flow(
        chat_id, process_id, bot, progress_id,
    )


def _model_to_dict(m: AsIsModel) -> dict:
    """Convert AS-IS model ORM object to dict."""
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
