"""Follow-up question flow and AS-IS generation trigger."""

import json
import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import async_session
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

logger = logging.getLogger(__name__)


async def send_next_gap_question(
    chat_id: int, process_id: int, update_or_bot
) -> None:
    """Send the next pending gap question with inline buttons."""
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
        await trigger_asis_generation(chat_id, process_id, update_or_bot)
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Ответить", callback_data=f"answer_{gap.id}"),
                InlineKeyboardButton("Пропустить", callback_data=f"skip_{gap.id}"),
            ],
            [
                InlineKeyboardButton(
                    "Завершить позже", callback_data=f"pause_{process_id}"
                )
            ],
        ]
    )

    bot = _get_bot(update_or_bot)
    await bot.send_message(
        chat_id=chat_id,
        text=f"❓ {gap.question_text}",
        reply_markup=keyboard,
    )


async def handle_gap_answer(
    update: Update, gap_id: int, answer_text: str
) -> None:
    """Process answer to a gap question."""
    async with async_session() as db:
        gap = await db.get(Gap, gap_id)
        if not gap:
            return

        gap.status = GapStatus.ANSWERED
        process_id = gap.process_id

        # Store as raw input linked to session
        from bot.models import RawInput

        # Find active session
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

    # Re-process with updated inputs
    from bot.handlers.interview import _process_input

    if session:
        await _process_input(update, process_id, session.id)


async def handle_gap_skip(chat_id: int, gap_id: int, update_or_bot) -> None:
    """Mark a gap as skipped and move to next question."""
    async with async_session() as db:
        gap = await db.get(Gap, gap_id)
        if not gap:
            return
        gap.status = GapStatus.SKIPPED
        process_id = gap.process_id
        await db.commit()

    bot = _get_bot(update_or_bot)
    await bot.send_message(chat_id=chat_id, text="⏭ Пропущено.")
    await send_next_gap_question(chat_id, process_id, update_or_bot)


async def handle_pause(chat_id: int, process_id: int, update_or_bot) -> None:
    """Pause the interview session."""
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
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "⏸ Сессия приостановлена. "
            "Вы можете вернуться в любое время — я продолжу с того же места."
        ),
    )


async def trigger_asis_generation(
    chat_id: int, process_id: int, update_or_bot
) -> None:
    """Generate AS-IS page: narrative + mermaid + HTML."""
    bot = _get_bot(update_or_bot)

    async with async_session() as db:
        process = await db.get(Process, process_id)
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()

        if not asis or not process:
            await bot.send_message(
                chat_id=chat_id,
                text="Недостаточно данных для генерации AS-IS.",
            )
            return

        model_data = _model_to_dict(asis)

    # LLM Call 3: Generate narrative
    await bot.send_message(chat_id=chat_id, text="📄 Генерирую описание...")
    narrative = await generate_narrative(process.name, model_data)

    # LLM Call 4: Generate Mermaid
    await bot.send_message(chat_id=chat_id, text="📊 Генерирую диаграмму...")
    mermaid_code = await generate_mermaid(process.name, model_data)

    # Publish page
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
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось опубликовать страницу. Попробуем позже.",
            )

        await db.commit()

    if url:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📄 Открыть AS-IS", url=url)],
                [
                    InlineKeyboardButton(
                        "🔍 Продолжить: выбор автоматизации",
                        callback_data=f"start_opps_{process_id}",
                    )
                ],
            ]
        )
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ AS-IS по процессу *{process.name}* готов!\n\n"
                f"Страница: {url}\n\n"
                "Теперь выберите, какие точки автоматизации вам интересны."
            ),
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

        # Auto-start opportunity generation
        await _generate_and_show_opportunities(chat_id, process_id, bot)


async def _generate_and_show_opportunities(
    chat_id: int, process_id: int, bot
) -> None:
    """Generate automation opportunities and send them to the user."""
    async with async_session() as db:
        process = await db.get(Process, process_id)
        result = await db.execute(
            select(AsIsModel).where(AsIsModel.process_id == process_id)
        )
        asis = result.scalar_one_or_none()
        if not asis or not process:
            return

        model_data = _model_to_dict(asis)

    # LLM Call 5: Generate opportunities
    opps = await generate_opportunities(process.name, model_data)

    if not opps:
        await bot.send_message(
            chat_id=chat_id,
            text="Не удалось выявить точки автоматизации.",
        )
        return

    # Save and display
    async with async_session() as db:
        process = await db.get(Process, process_id)
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

    # Send opportunity cards
    from bot.handlers.opportunities import send_next_opportunity
    await send_next_opportunity(chat_id, process_id, bot)


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
    if hasattr(update_or_bot, "bot"):
        return update_or_bot.bot
    return update_or_bot
