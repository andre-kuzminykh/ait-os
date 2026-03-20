"""Interview flow handlers — process text/voice input with progress UX."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import COMPLETENESS_THRESHOLD
from bot.database import async_session
from bot.handlers.progress import delete_messages, send_progress, send_step, typewriter_send
from bot.models import AsIsModel, InterviewSession, Process, RawInput
from bot.services.extractor import extract_asis_model
from bot.services.gap_detector import detect_gaps
from bot.services.transcription import transcribe_telegram_voice
from bot.states import GapStatus, ProcessStatus, SessionStatus

logger = logging.getLogger(__name__)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle plain text messages during interview."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)
    if not ctx:
        await update.message.reply_text(
            "Начните с /start или /new\\_process, чтобы создать процесс.",
            parse_mode="Markdown",
        )
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
        bot, chat_id, 0, 2,
        "⏳ Записал ввод",
        "Сохраняю текст и начинаю анализ...",
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
        bot, chat_id, 0, 3,
        "🎤 Получил аудио",
        "Отправляю на распознавание речи (Whisper API)...",
        progress_id,
    )

    ctx["bot_message_id"] = progress_id
    await save_chat_context(chat_id, ctx)

    transcript = await transcribe_telegram_voice(bot, voice.file_id)

    if not transcript:
        await send_progress(
            bot, chat_id,
            "❌ Не удалось распознать аудио. Попробуйте отправить текстом.",
            progress_id,
        )
        return

    # Typewriter reveal of transcription
    progress_id = await send_step(
        bot, chat_id, 1, 3,
        "📝 Распознаю текст...",
        "Обрабатываю результат транскрипции...",
        progress_id,
    )
    progress_id = await typewriter_send(
        bot, chat_id, transcript, prefix="📝 Распознано:\n", message_id=progress_id,
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
        bot, chat_id, 2, 3,
        "⏳ Анализирую...",
        "Передаю текст в LLM для извлечения структуры процесса...",
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
        await update.message.reply_text(
            "Пока поддерживаются только аудиофайлы и голосовые сообщения."
        )
        return

    # Treat as voice
    update.message.audio = doc  # duck-type for transcription
    await handle_voice_message(update, context)


async def _process_input(
    bot, chat_id: int, process_id: int, session_id: int,
    progress_id: int | None = None,
) -> None:
    """Extract AS-IS model, detect gaps, and decide next action.

    Shows step-by-step progress by editing a single message.
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
        old_completeness = 0.0
        if existing:
            old_completeness = existing.completeness_score or 0.0
            existing_json = json.dumps(
                _model_to_dict(existing), ensure_ascii=False
            )

    # LLM Call 1: Extract/update AS-IS model
    progress_id = await send_step(
        bot, chat_id, 1, 2,
        "⏳ Извлекаю структуру процесса",
        "LLM анализирует текст → цель, этапы, роли, системы, артефакты, метрики, боли...",
        progress_id,
    )

    model_data = await extract_asis_model(
        process.name, raw_texts, existing_json
    )

    if not model_data:
        await send_progress(
            bot, chat_id,
            "❌ Не удалось проанализировать ответ. Попробуйте описать подробнее.",
            progress_id,
        )
        return

    # LLM Call 2: Detect gaps
    progress_id = await send_step(
        bot, chat_id, 2, 2,
        "⏳ Оцениваю полноту описания",
        "LLM проверяет: все ли роли, системы, метрики, SLA, точки передачи указаны...",
        progress_id,
    )

    gap_result = await detect_gaps(process.name, model_data)
    completeness = gap_result.get("completeness_score", 0.0)
    gaps = gap_result.get("gaps", [])

    # Never allow completeness to decrease
    effective_completeness = max(completeness, old_completeness)

    async with async_session() as db:
        # Save/update AS-IS model
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
        asis.completeness_score = effective_completeness

        # Save new gaps
        from bot.models import Gap
        from bot.states import GapFieldType

        for g in gaps:
            field_type_str = g.get("field_type", "")
            try:
                ft = GapFieldType(field_type_str)
            except ValueError:
                ft = GapFieldType.PAIN_POINTS

            gap = Gap(
                process_id=process_id,
                stage_id=g.get("stage_id"),
                field_type=ft,
                question_text=g.get("question", ""),
                confidence_score=g.get("confidence", 0.5),
                status=GapStatus.PENDING,
            )
            db.add(gap)

        process = await db.get(Process, process_id)
        session = await db.get(InterviewSession, session_id)

        display_score = int(effective_completeness * 100)

        if effective_completeness >= COMPLETENESS_THRESHOLD or not gaps:
            # Ready for AS-IS generation
            process.status = ProcessStatus.ASIS_READY
            session.state = SessionStatus.COMPLETED
            await db.commit()

            progress_id = await send_step(
                bot, chat_id, 2, 2,
                f"✅ Полнота описания: {display_score}%",
                "Достаточно данных! Перехожу к генерации AS-IS страницы...",
                progress_id,
            )

            from bot.handlers.clarification import trigger_asis_generation
            await trigger_asis_generation(
                chat_id, process_id, bot, progress_id
            )
        else:
            # Need clarification
            process.status = ProcessStatus.CLARIFICATION_IN_PROGRESS
            session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
            await db.commit()

            # Edit progress message to show completeness, then to gap question
            progress_id = await send_step(
                bot, chat_id, 2, 2,
                f"📊 Полнота: {display_score}%",
                "Задам уточняющие вопросы...",
                progress_id,
            )

            # Store bot_message_id so gap question edits the same message
            ctx = await get_chat_context(chat_id) or {}
            ctx["bot_message_id"] = progress_id
            await save_chat_context(chat_id, ctx)

            from bot.handlers.clarification import send_next_gap_question
            await send_next_gap_question(
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
