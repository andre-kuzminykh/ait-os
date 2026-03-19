"""Deep link and /start handler."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import async_session
from bot.models import (
    Company,
    InterviewSession,
    Process,
    Respondent,
)
from bot.states import ProcessStatus, SessionStatus

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start and deep links like /start process_<token>."""
    args = context.args
    tg_user = update.effective_user

    async with async_session() as db:
        # Upsert respondent
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

            # Bind session to this respondent if not yet bound
            if session.respondent_id != respondent.id:
                session.respondent_id = respondent.id
                await db.flush()

            process = session.process

            # Check if there's an active session to resume
            if session.state in (
                SessionStatus.PAUSED,
                SessionStatus.AWAITING_FOLLOWUP_ANSWER,
            ):
                await _resume_session(update, session, process)
            else:
                await _start_interview(update, db, session, process, respondent)

            await db.commit()
            return

        # No deep link — show welcome or list processes
        await _show_welcome(update, db, respondent)
        await db.commit()


async def cmd_new_process(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /new_process <name> — create a new process for quick testing."""
    tg_user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "Использование: /new_process Название процесса"
        )
        return

    process_name = " ".join(context.args)

    async with async_session() as db:
        # Upsert respondent
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

        # Upsert default company
        result = await db.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()
        if company is None:
            company = Company(name="Default")
            db.add(company)
            await db.flush()

        process = Process(
            company_id=company.id,
            name=process_name,
            status=ProcessStatus.CREATED,
        )
        db.add(process)
        await db.flush()

        session = InterviewSession(
            process_id=process.id,
            respondent_id=respondent.id,
            state=SessionStatus.STARTED,
        )
        db.add(session)
        await db.flush()

        await _start_interview(update, db, session, process, respondent)
        await db.commit()


async def _start_interview(
    update: Update,
    db,
    session: InterviewSession,
    process: Process,
    respondent: Respondent,
) -> None:
    """Send opening message and set session to awaiting initial response."""
    session.state = SessionStatus.AWAITING_INITIAL_RESPONSE
    process.status = ProcessStatus.INTERVIEW_IN_PROGRESS

    # Store session id in user context
    update.effective_chat  # ensure chat exists
    context_data = {"session_id": session.id, "process_id": process.id}
    # We'll store in bot_data keyed by chat_id
    chat_id = update.effective_chat.id

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

    # Save context for this chat
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

    # Count pending gaps
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

    # Check for published page
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
        await send_next_gap_question(update.effective_chat.id, process.id, update)


async def _show_welcome(update: Update, db, respondent: Respondent) -> None:
    """Show welcome message with existing processes."""
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.respondent_id == respondent.id)
        .options(selectinload(InterviewSession.process))
    )
    sessions = result.scalars().all()

    if not sessions:
        await update.message.reply_text(
            "Привет! Я — Andre AI.\n\n"
            "Я помогу описать ваш бизнес-процесс, создать AS-IS документ "
            "и найти точки автоматизации.\n\n"
            "Чтобы начать, используйте:\n"
            "/new\\_process Название процесса\n\n"
            "Или откройте ссылку на интервью, которую вам прислали.",
            parse_mode="Markdown",
        )
        return

    buttons = []
    for s in sessions:
        label = f"{s.process.name} [{s.process.status.value}]"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"resume_{s.id}")]
        )

    await update.message.reply_text(
        "Ваши процессы:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
