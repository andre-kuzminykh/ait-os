"""Process list, process creation, and /start handler."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.handlers.progress import delete_messages
from bot.models import (
    AsIsModel,
    Company,
    InterviewSession,
    Process,
    PublishedPage,
    Respondent,
)
from bot.states import ProcessStatus, SessionStatus

logger = logging.getLogger(__name__)

_STATUS_ICONS = {
    ProcessStatus.CREATED: "⚪",
    ProcessStatus.INTERVIEW_IN_PROGRESS: "🟡",
    ProcessStatus.CLARIFICATION_IN_PROGRESS: "🟡",
    ProcessStatus.ASIS_READY: "🔵",
    ProcessStatus.ASIS_PUBLISHED: "🟢",
    ProcessStatus.AUTOMATION_SELECTION_IN_PROGRESS: "🔵",
    ProcessStatus.READY_FOR_TOBE: "✅",
}

_STATUS_LABELS = {
    ProcessStatus.CREATED: "Создан",
    ProcessStatus.INTERVIEW_IN_PROGRESS: "Интервью",
    ProcessStatus.CLARIFICATION_IN_PROGRESS: "Уточнение",
    ProcessStatus.ASIS_READY: "AS-IS готов",
    ProcessStatus.ASIS_PUBLISHED: "AS-IS опубликован",
    ProcessStatus.AUTOMATION_SELECTION_IN_PROGRESS: "Выбор автоматизации",
    ProcessStatus.READY_FOR_TOBE: "Готов к TO-BE",
}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show process list (main menu)."""
    args = context.args
    tg_user = update.effective_user
    chat_id = update.effective_chat.id

    async with async_session() as db:
        respondent = await _upsert_respondent(db, tg_user)

        # Deep link: process_<token>
        if args and args[0].startswith("process_"):
            token = args[0][len("process_"):]
            result = await db.execute(
                select(InterviewSession)
                .where(InterviewSession.token == token)
                .options(selectinload(InterviewSession.process))
            )
            session = result.scalar_one_or_none()

            if session is None:
                await update.message.reply_text(
                    "Ссылка недействительна или устарела."
                )
                return

            if session.respondent_id != respondent.id:
                session.respondent_id = respondent.id
                await db.flush()

            process = session.process

            if session.state in (
                SessionStatus.PAUSED,
                SessionStatus.AWAITING_FOLLOWUP_ANSWER,
            ):
                await _resume_session(update, session, process)
            else:
                await _start_interview(update, db, session, process, respondent)

            await db.commit()
            return

        await db.commit()

    # Delete user's /start message
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    # Show main process list
    await show_process_list(chat_id, context.bot, tg_user.id)


async def show_process_list(
    chat_id: int, bot, telegram_user_id: int, message_id: int | None = None,
) -> int:
    """Show process list with '+' button. Edit existing message or send new."""
    async with async_session() as db:
        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.respondent_id.in_(
                    select(Respondent.id).where(
                        Respondent.telegram_user_id == telegram_user_id
                    )
                )
            )
            .options(selectinload(InterviewSession.process))
        )
        sessions = result.scalars().all()

    # Deduplicate by process_id (take latest session per process)
    seen = {}
    for s in sessions:
        if s.process_id not in seen:
            seen[s.process_id] = s

    buttons = []
    for s in seen.values():
        icon = _STATUS_ICONS.get(s.process.status, "⚪")
        label = f"{icon} {s.process.name}"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"view_{s.process.id}")]
        )

    buttons.append(
        [InlineKeyboardButton("➕ Новый процесс", callback_data="new_process")]
    )

    text = "📋 *Процессы*" if seen else "📋 *Процессы*\n\nПока пусто. Создайте первый процесс!"
    keyboard = InlineKeyboardMarkup(buttons)

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return message_id
        except Exception:
            pass

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return msg.message_id


async def show_process_detail(
    chat_id: int, process_id: int, message_id: int, bot,
    telegram_user_id: int,
) -> None:
    """Show process detail view with action buttons."""
    async with async_session() as db:
        process = await db.get(Process, process_id)
        if not process:
            return

        # Get AS-IS model info
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        completeness = int((asis.completeness_score or 0) * 100) if asis else 0

        # Get published page URL
        result = await db.execute(
            select(PublishedPage)
            .where(PublishedPage.process_id == process_id)
            .limit(1)
        )
        page = result.scalar_one_or_none()
        page_url = page.html_url if page else None

    status_label = _STATUS_LABELS.get(process.status, process.status.value)
    icon = _STATUS_ICONS.get(process.status, "⚪")

    text = f"{icon} *{process.name}*\n\nСтатус: {status_label}"
    if completeness:
        text += f"\nПолнота: {completeness}%"
    if page_url:
        text += f"\nAS-IS: {page_url}"

    buttons = []

    # Action buttons based on status
    if process.status in (
        ProcessStatus.CREATED,
        ProcessStatus.INTERVIEW_IN_PROGRESS,
        ProcessStatus.CLARIFICATION_IN_PROGRESS,
    ):
        buttons.append(
            [InlineKeyboardButton(
                "▶️ Продолжить заполнение",
                callback_data=f"continue_{process_id}",
            )]
        )
    elif process.status == ProcessStatus.ASIS_PUBLISHED:
        if page_url:
            buttons.append([InlineKeyboardButton("📄 Открыть AS-IS", url=page_url)])
        buttons.append(
            [InlineKeyboardButton(
                "🔍 Выбор автоматизации",
                callback_data=f"start_opps_{process_id}",
            )]
        )
    elif process.status == ProcessStatus.AUTOMATION_SELECTION_IN_PROGRESS:
        buttons.append(
            [InlineKeyboardButton(
                "▶️ Продолжить выбор",
                callback_data=f"start_opps_{process_id}",
            )]
        )
    elif process.status == ProcessStatus.READY_FOR_TOBE:
        if page_url:
            buttons.append([InlineKeyboardButton("📄 Открыть AS-IS", url=page_url)])
        buttons.append(
            [InlineKeyboardButton(
                "📋 Составить TO-BE",
                callback_data=f"tobe_{process_id}",
            )]
        )
    elif process.status == ProcessStatus.ASIS_READY:
        buttons.append(
            [InlineKeyboardButton(
                "▶️ Продолжить",
                callback_data=f"continue_{process_id}",
            )]
        )

    buttons.append(
        [InlineKeyboardButton("← Назад", callback_data="back_to_list")]
    )

    keyboard = InlineKeyboardMarkup(buttons)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )


async def handle_new_process_name(
    bot, chat_id: int, name: str, telegram_user_id: int,
    user_message_id: int,
) -> None:
    """Create a new process from the name the user just typed."""
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    # Get messages to delete (bot prompt + user's name message)
    ctx = await get_chat_context(chat_id) or {}
    msgs_to_delete = ctx.pop("messages_to_delete", [])
    msgs_to_delete.append(user_message_id)
    ctx.pop("awaiting_process_name", None)

    async with async_session() as db:
        respondent = await _get_respondent(db, telegram_user_id)
        if not respondent:
            respondent = Respondent(
                telegram_user_id=telegram_user_id,
                display_name="",
            )
            db.add(respondent)
            await db.flush()

        result = await db.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()
        if company is None:
            company = Company(name="Default")
            db.add(company)
            await db.flush()

        process = Process(
            company_id=company.id,
            name=name,
            status=ProcessStatus.INTERVIEW_IN_PROGRESS,
        )
        db.add(process)
        await db.flush()

        session = InterviewSession(
            process_id=process.id,
            respondent_id=respondent.id,
            state=SessionStatus.AWAITING_INITIAL_RESPONSE,
        )
        db.add(session)
        await db.flush()

        ctx["session_id"] = session.id
        ctx["process_id"] = process.id
        ctx["respondent_id"] = respondent.id
        await save_chat_context(chat_id, ctx)

        await db.commit()

    # Delete tracked messages
    await delete_messages(bot, chat_id, msgs_to_delete)

    # Send interview greeting
    greeting = (
        f"👋 Процесс *{name}* создан\\.\n\n"
        "Расскажите, как устроен этот процесс\\.\n"
        "Можно текстом или голосом\\.\n\n"
        "_Я задам уточняющие вопросы позже\\._"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=greeting,
        parse_mode="MarkdownV2",
    )


async def _upsert_respondent(db, tg_user) -> Respondent:
    """Get or create respondent."""
    result = await db.execute(
        select(Respondent).where(Respondent.telegram_user_id == tg_user.id)
    )
    respondent = result.scalar_one_or_none()
    if respondent is None:
        respondent = Respondent(
            telegram_user_id=tg_user.id,
            display_name=tg_user.full_name,
        )
        db.add(respondent)
        await db.flush()
    return respondent


async def _get_respondent(db, telegram_user_id: int) -> Respondent | None:
    result = await db.execute(
        select(Respondent).where(Respondent.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def _start_interview(
    update: Update,
    db,
    session: InterviewSession,
    process: Process,
    respondent: Respondent,
) -> None:
    """Start interview via deep link."""
    session.state = SessionStatus.AWAITING_INITIAL_RESPONSE
    process.status = ProcessStatus.INTERVIEW_IN_PROGRESS

    chat_id = update.effective_chat.id
    context_data = {
        "session_id": session.id,
        "process_id": process.id,
        "respondent_id": respondent.id,
    }

    greeting = (
        f"👋 Мы собираем текущую картину процесса *{process.name}*.\n\n"
        "Можно отвечать текстом или голосом.\n\n"
        "Расскажите в целом, как у вас устроен этот процесс:\n"
        "• Какие этапы есть?\n"
        "• Кто участвует?\n"
        "• Какие системы используете?\n"
        "• Какие артефакты создаются?\n"
        "• Какие есть метрики и проблемы?\n\n"
        "_Опишите процесс как можете — я задам уточняющие вопросы позже._"
    )

    await update.message.reply_text(greeting, parse_mode="Markdown")

    from bot.handlers.callbacks import save_chat_context
    await save_chat_context(chat_id, context_data)


async def _resume_session(
    update: Update,
    session: InterviewSession,
    process: Process,
) -> None:
    """Resume a paused or pending session."""
    from bot.handlers.clarification import send_next_gap_question
    from bot.handlers.callbacks import save_chat_context

    chat_id = update.effective_chat.id
    context_data = {"session_id": session.id, "process_id": process.id}
    await save_chat_context(chat_id, context_data)

    from sqlalchemy import select, func
    from bot.models import Gap
    from bot.states import GapStatus
    from bot.database import async_session as get_session

    async with get_session() as db:
        result = await db.execute(
            select(func.count()).where(
                Gap.process_id == process.id,
                Gap.status == GapStatus.PENDING,
            )
        )
        pending_count = result.scalar()

    status_parts = [f"Процесс: *{process.name}*"]
    if pending_count:
        status_parts.append(f"Осталось вопросов: {pending_count}")

    from bot.models import PublishedPage
    async with get_session() as db:
        result = await db.execute(
            select(PublishedPage).where(PublishedPage.process_id == process.id).limit(1)
        )
        page = result.scalar_one_or_none()
        if page and page.html_url:
            status_parts.append(f"AS-IS страница: {page.html_url}")

    msg = "Продолжаем! " + "\n".join(status_parts)
    await update.message.reply_text(msg, parse_mode="Markdown")

    if session.state == SessionStatus.AWAITING_FOLLOWUP_ANSWER:
        await send_next_gap_question(chat_id, process.id, update)
