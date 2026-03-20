"""Automation opportunity selection handlers."""

from __future__ import annotations

import logging

from sqlalchemy import select, func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.models import AutomationOpportunity, Process
from bot.states import OpportunityStatus, ProcessStatus

logger = logging.getLogger(__name__)


async def send_next_opportunity(chat_id: int, process_id: int, bot) -> None:
    """Send the next proposed opportunity as a card with inline buttons."""
    async with async_session() as db:
        result = await db.execute(
            select(AutomationOpportunity).where(
                AutomationOpportunity.process_id == process_id,
                AutomationOpportunity.status == OpportunityStatus.PROPOSED,
            )
        )
        opp = result.scalars().first()

    if opp is None:
        # All opportunities reviewed
        await _show_selection_summary(chat_id, process_id, bot)
        return

    type_label = ""
    if opp.opp_type:
        type_map = {
            "ai": "🤖 AI",
            "rule_based": "⚙️ Правила",
            "integration": "🔗 Интеграция",
            "analytics": "📊 Аналитика",
            "monitoring": "📡 Мониторинг",
        }
        type_label = type_map.get(opp.opp_type.value, "")

    card = f"*{opp.title}*"
    if type_label:
        card += f" ({type_label})"
    if opp.stage_id:
        card += f"\nЭтап: {opp.stage_id}"
    if opp.problem:
        card += f"\nПроблема: {opp.problem}"
    if opp.expected_benefit:
        card += f"\nЭффект: {opp.expected_benefit}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Выбрать", callback_data=f"opp_select_{opp.id}"
                ),
                InlineKeyboardButton(
                    "❌ Не выбирать", callback_data=f"opp_reject_{opp.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "ℹ️ Подробнее", callback_data=f"opp_detail_{opp.id}"
                ),
            ],
        ]
    )

    await bot.send_message(
        chat_id=chat_id,
        text=card,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_opportunity_select(
    chat_id: int, opp_id: int, bot
) -> None:
    """Mark opportunity as selected."""
    process_id = await _set_opp_status(opp_id, OpportunityStatus.SELECTED)
    await bot.send_message(chat_id=chat_id, text="✅ Выбрано!")
    if process_id:
        await send_next_opportunity(chat_id, process_id, bot)


async def handle_opportunity_reject(
    chat_id: int, opp_id: int, bot
) -> None:
    """Mark opportunity as rejected."""
    process_id = await _set_opp_status(opp_id, OpportunityStatus.REJECTED)
    await bot.send_message(chat_id=chat_id, text="❌ Пропущено.")
    if process_id:
        await send_next_opportunity(chat_id, process_id, bot)


async def handle_opportunity_detail(
    chat_id: int, opp_id: int, bot
) -> None:
    """Show detailed description of an opportunity."""
    async with async_session() as db:
        opp = await db.get(AutomationOpportunity, opp_id)
        if not opp:
            return

    detail = f"*{opp.title}*\n\n"
    if opp.description:
        detail += f"{opp.description}\n\n"
    if opp.problem:
        detail += f"*Проблема:* {opp.problem}\n"
    if opp.expected_benefit:
        detail += f"*Ожидаемый эффект:* {opp.expected_benefit}\n"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Выбрать", callback_data=f"opp_select_{opp.id}"
                ),
                InlineKeyboardButton(
                    "❌ Не выбирать", callback_data=f"opp_reject_{opp.id}"
                ),
            ],
        ]
    )

    await bot.send_message(
        chat_id=chat_id,
        text=detail,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _set_opp_status(opp_id: int, status: OpportunityStatus) -> int | None:
    """Set opportunity status and return process_id."""
    async with async_session() as db:
        opp = await db.get(AutomationOpportunity, opp_id)
        if not opp:
            return None
        opp.status = status
        process_id = opp.process_id
        await db.commit()
    return process_id


async def _show_selection_summary(
    chat_id: int, process_id: int, bot
) -> None:
    """Show summary of selected opportunities and CTA."""
    async with async_session() as db:
        result = await db.execute(
            select(AutomationOpportunity).where(
                AutomationOpportunity.process_id == process_id,
                AutomationOpportunity.status == OpportunityStatus.SELECTED,
            )
        )
        selected = result.scalars().all()

        # Count total
        result = await db.execute(
            select(func.count()).where(
                AutomationOpportunity.process_id == process_id
            )
        )
        total = result.scalar()

        process = await db.get(Process, process_id)
        process.status = ProcessStatus.READY_FOR_TOBE
        await db.commit()

    if selected:
        summary = f"Выбрано {len(selected)} из {total} возможностей:\n\n"
        for i, opp in enumerate(selected, 1):
            summary += f"{i}. *{opp.title}*\n"
    else:
        summary = "Ни одна возможность не выбрана.\n"

    summary += "\nПроцесс готов к составлению TO-BE."

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📋 Составить TO-BE",
                    callback_data=f"tobe_{process_id}",
                )
            ]
        ]
    )

    await bot.send_message(
        chat_id=chat_id,
        text=summary,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
