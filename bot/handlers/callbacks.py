"""Inline button callback dispatcher and chat context management."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.models import InterviewSession, Process
from bot.states import ProcessStatus, SessionStatus

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


async def track_message_for_deletion(chat_id: int, message_id: int) -> None:
    """Add a message to the deletion queue for this chat."""
    ctx = _chat_contexts.get(chat_id) or {}
    msgs = ctx.get("messages_to_delete", [])
    msgs.append(message_id)
    ctx["messages_to_delete"] = msgs
    _chat_contexts[chat_id] = ctx


async def get_and_clear_deletion_queue(chat_id: int) -> list[int]:
    """Pop all message IDs queued for deletion."""
    ctx = _chat_contexts.get(chat_id) or {}
    msgs = ctx.pop("messages_to_delete", [])
    _chat_contexts[chat_id] = ctx
    return msgs


async def callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route inline button callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = query.message.chat_id
    bot = context.bot
    message_id = query.message.message_id

    # ---- Process list / navigation ----

    if data == "new_process":
        await _handle_new_process(chat_id, message_id, bot)

    elif data == "back_to_list":
        ctx = await get_chat_context(chat_id) or {}
        tg_user_id = ctx.get("telegram_user_id")
        if not tg_user_id:
            tg_user_id = update.effective_user.id if update.effective_user else None
        if tg_user_id:
            from bot.handlers.start import show_process_list
            await show_process_list(chat_id, bot, tg_user_id, message_id)

    elif data.startswith("view_"):
        process_id = int(data.split("_", 1)[1])
        ctx = await get_chat_context(chat_id) or {}
        tg_user_id = ctx.get("telegram_user_id")
        if not tg_user_id:
            tg_user_id = update.effective_user.id if update.effective_user else None
        from bot.handlers.start import show_process_detail
        await show_process_detail(chat_id, process_id, message_id, bot, tg_user_id)

    elif data.startswith("continue_"):
        process_id = int(data.split("_", 1)[1])
        await _handle_continue(chat_id, process_id, message_id, bot, update)

    # ---- Legacy / interview flow ----

    elif data.startswith("resume_"):
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
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🚀 Процесс в статусе *ready\\_for\\_tobe*.\n\n"
                "Генерация TO-BE будет доступна в следующем обновлении."
            ),
            parse_mode="Markdown",
        )


async def _handle_new_process(chat_id: int, message_id: int, bot) -> None:
    """Prompt user to enter process name."""
    ctx = _chat_contexts.get(chat_id) or {}
    ctx["awaiting_process_name"] = True
    ctx["messages_to_delete"] = ctx.get("messages_to_delete", [])
    ctx["messages_to_delete"].append(message_id)
    _chat_contexts[chat_id] = ctx

    msg = await bot.send_message(
        chat_id=chat_id,
        text="Введите название процесса:",
    )
    ctx["messages_to_delete"].append(msg.message_id)
    _chat_contexts[chat_id] = ctx


async def _handle_continue(
    chat_id: int, process_id: int, message_id: int, bot, update: Update,
) -> None:
    """Continue filling a process — set up context and resume."""
    # Delete the detail view message
    from bot.handlers.progress import delete_messages
    await delete_messages(bot, chat_id, [message_id])

    async with async_session() as db:
        process = await db.get(Process, process_id)
        if not process:
            return

        from sqlalchemy import select
        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.process_id == process_id,
                InterviewSession.state != SessionStatus.COMPLETED,
            )
            .limit(1)
        )
        session = result.scalar_one_or_none()

        if not session:
            # Create new session
            from bot.models import Respondent
            tg_user_id = update.effective_user.id if update.effective_user else None
            if tg_user_id:
                result = await db.execute(
                    select(Respondent).where(
                        Respondent.telegram_user_id == tg_user_id
                    )
                )
                respondent = result.scalar_one_or_none()
                if respondent:
                    session = InterviewSession(
                        process_id=process_id,
                        respondent_id=respondent.id,
                        state=SessionStatus.AWAITING_INITIAL_RESPONSE,
                    )
                    db.add(session)
                    await db.flush()

        if not session:
            return

        ctx = {
            "session_id": session.id,
            "process_id": process.id,
        }
        if update.effective_user:
            ctx["telegram_user_id"] = update.effective_user.id
        await save_chat_context(chat_id, ctx)

        if process.status == ProcessStatus.CREATED:
            process.status = ProcessStatus.INTERVIEW_IN_PROGRESS
            session.state = SessionStatus.AWAITING_INITIAL_RESPONSE
            await db.commit()

            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"▶️ Продолжаем с процессом *{process.name}*\\.\n\n"
                    "Расскажите, как устроен этот процесс\\."
                ),
                parse_mode="MarkdownV2",
            )
        elif process.status in (
            ProcessStatus.CLARIFICATION_IN_PROGRESS,
            ProcessStatus.ASIS_READY,
        ):
            if session.state == SessionStatus.PAUSED:
                session.state = SessionStatus.AWAITING_FOLLOWUP_ANSWER
            await db.commit()

            from bot.handlers.clarification import send_next_gap_question
            await send_next_gap_question(chat_id, process_id, bot)
        else:
            await db.commit()
            await bot.send_message(
                chat_id=chat_id,
                text=f"▶️ Продолжаем с процессом *{process.name}*\\.",
                parse_mode="MarkdownV2",
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

        from sqlalchemy import select

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
    ctx = await get_chat_context(chat_id) or {}
    ctx["pending_gap_id"] = gap_id
    await save_chat_context(chat_id, ctx)

    await bot.send_message(
        chat_id=chat_id,
        text="Напишите ответ текстом или отправьте голосовое сообщение.",
    )
