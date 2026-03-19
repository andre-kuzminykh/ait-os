"""Inline button callback dispatcher and chat context management."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.models import InterviewSession
from bot.states import SessionStatus

logger = logging.getLogger(__name__)

# In-memory chat context storage (chat_id -> context dict)
# In production, use Redis or DB-backed storage.
_chat_contexts: dict[int, dict] = {}


async def save_chat_context(chat_id: int, ctx: dict) -> None:
    """Save session context for a chat."""
    _chat_contexts[chat_id] = ctx


async def get_chat_context(chat_id: int) -> dict | None:
    """Get session context for a chat."""
    return _chat_contexts.get(chat_id)


async def callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route inline button callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
    bot = context.bot

    if data.startswith("resume_"):
        session_id = int(data.split("_", 1)[1])
        await _handle_resume(chat_id, session_id, update, bot)

    elif data.startswith("answer_"):
        gap_id = int(data.split("_", 1)[1])
        await _handle_answer_prompt(chat_id, gap_id, bot)

    elif data.startswith("skip_"):
        gap_id = int(data.split("_", 1)[1])
        from bot.handlers.clarification import handle_gap_skip
        await handle_gap_skip(chat_id, gap_id, bot)

    elif data.startswith("pause_"):
        process_id = int(data.split("_", 1)[1])
        from bot.handlers.clarification import handle_pause
        await handle_pause(chat_id, process_id, bot)

    elif data.startswith("start_opps_"):
        process_id = int(data.split("_", 2)[2])
        from bot.handlers.opportunities import send_next_opportunity
        await send_next_opportunity(chat_id, process_id, bot)

    elif data.startswith("opp_select_"):
        opp_id = int(data.split("_", 2)[2])
        from bot.handlers.opportunities import handle_opportunity_select
        await handle_opportunity_select(chat_id, opp_id, bot)

    elif data.startswith("opp_reject_"):
        opp_id = int(data.split("_", 2)[2])
        from bot.handlers.opportunities import handle_opportunity_reject
        await handle_opportunity_reject(chat_id, opp_id, bot)

    elif data.startswith("opp_detail_"):
        opp_id = int(data.split("_", 2)[2])
        from bot.handlers.opportunities import handle_opportunity_detail
        await handle_opportunity_detail(chat_id, opp_id, bot)

    elif data.startswith("tobe_"):
        # End of this feature — just acknowledge
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🚀 Процесс в статусе *ready\\_for\\_tobe*.\n\n"
                "Генерация TO-BE будет доступна в следующем обновлении."
            ),
            parse_mode="Markdown",
        )


async def _handle_resume(
    chat_id: int, session_id: int, update: Update, bot
) -> None:
    """Resume an existing session from the process list."""
    async with async_session() as db:
        session = await db.get(InterviewSession, session_id)
        if not session:
            await bot.send_message(chat_id=chat_id, text="Сессия не найдена.")
            return

        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        from bot.models import Process

        process = await db.get(Process, session.process_id)
        if not process:
            return

        ctx = {"session_id": session.id, "process_id": process.id}
        await save_chat_context(chat_id, ctx)

        if session.state == SessionStatus.PAUSED:
            session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
            await db.commit()

    await bot.send_message(
        chat_id=chat_id,
        text=f"Продолжаем работу с процессом *{process.name}*.",
        parse_mode="Markdown",
    )

    from bot.handlers.clarification import send_next_gap_question
    await send_next_gap_question(chat_id, process.id, bot)


async def _handle_answer_prompt(chat_id: int, gap_id: int, bot) -> None:
    """Prompt user to type their answer to a gap question."""
    # Store gap_id so the next text message is treated as an answer
    ctx = await get_chat_context(chat_id) or {}
    ctx["pending_gap_id"] = gap_id
    await save_chat_context(chat_id, ctx)

    await bot.send_message(
        chat_id=chat_id,
        text="Напишите ответ текстом или отправьте голосовое сообщение.",
    )
