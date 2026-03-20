"""Automation opportunity selection handlers.

New flow: all opportunities shown at once as multiselect toggle buttons.
User toggles individual items, then presses "Далее" (only visible when >= 1
selected). After "Далее" → stub placeholder for TO-BE generation.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, func
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database import async_session
from bot.models import AutomationOpportunity, Process
from bot.states import OpportunityStatus, ProcessStatus

logger = logging.getLogger(__name__)

# Type emoji mapping (short — just the emoji)
_TYPE_EMOJI = {
    "ai": "🤖",
    "rule_based": "⚙️",
    "integration": "🔗",
    "analytics": "📊",
    "monitoring": "📡",
}


async def show_opportunities_multiselect(
    chat_id: int, process_id: int, bot,
    message_id: int | None = None,
    asis_url: str | None = None,
) -> None:
    """Show all opportunities as multiselect toggle buttons.

    Each opportunity is a short inline button. Toggled items show ✅ prefix.
    "Далее" button appears only when at least 1 is selected.
    If asis_url is provided, an "Открыть AS-IS" link button is shown at top.
    """
    from bot.handlers.callbacks import get_chat_context, save_chat_context

    async with async_session() as db:
        result = await db.execute(
            select(AutomationOpportunity).where(
                AutomationOpportunity.process_id == process_id,
            )
        )
        opps = result.scalars().all()

        process = await db.get(Process, process_id)

    if not opps:
        text = "Не удалось выявить точки автоматизации."
        if message_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=text,
                )
                return
            except Exception:
                pass
        await bot.send_message(chat_id=chat_id, text=text)
        return

    # Build description text — compact: title + emoji, then benefit
    text = "🔍 *Потенциал автоматизации*\n\n"

    for i, opp in enumerate(opps, 1):
        emoji = _TYPE_EMOJI.get(opp.opp_type.value, "") if opp.opp_type else ""
        text += f"{i}. {opp.title} {emoji}\n"
        if opp.expected_benefit:
            text += f"   _{opp.expected_benefit}_\n"

    text += "\nВыберите интересующие вас пункты:"

    # AS-IS link at the bottom
    if asis_url:
        text += f"\n\n[📄 Открыть AS-IS]({asis_url})"

    # Build toggle buttons — title + emoji on the right
    buttons = []
    selected_count = 0
    for opp in opps:
        is_selected = opp.status == OpportunityStatus.SELECTED
        if is_selected:
            selected_count += 1
        prefix = "✅ " if is_selected else "⬜ "
        emoji = _TYPE_EMOJI.get(opp.opp_type.value, "") if opp.opp_type else ""
        label = f"{prefix}{opp.title} {emoji}"
        if len(label) > 60:
            label = label[:57] + "..."
        buttons.append(
            [InlineKeyboardButton(
                label, callback_data=f"opp_toggle_{opp.id}",
            )]
        )

    # "Далее" button — only if at least 1 selected
    if selected_count > 0:
        buttons.append(
            [InlineKeyboardButton(
                f"➡️ Далее ({selected_count} выбрано)",
                callback_data=f"opp_proceed_{process_id}",
            )]
        )

    keyboard = InlineKeyboardMarkup(buttons)

    sent_id = None
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            sent_id = message_id
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

    ctx = await get_chat_context(chat_id) or {}
    ctx["bot_message_id"] = sent_id
    ctx["process_id"] = process_id
    await save_chat_context(chat_id, ctx)


async def handle_opportunity_toggle(
    chat_id: int, opp_id: int, bot, message_id: int | None = None,
) -> None:
    """Toggle an opportunity between SELECTED and PROPOSED."""
    async with async_session() as db:
        opp = await db.get(AutomationOpportunity, opp_id)
        if not opp:
            return

        if opp.status == OpportunityStatus.SELECTED:
            opp.status = OpportunityStatus.PROPOSED
        else:
            opp.status = OpportunityStatus.SELECTED

        process_id = opp.process_id
        await db.commit()

    # Re-render the multiselect view
    await show_opportunities_multiselect(chat_id, process_id, bot, message_id)


async def handle_opportunity_proceed(
    chat_id: int, process_id: int, bot, message_id: int | None = None,
) -> None:
    """Proceed after opportunity selection — mark unselected as rejected,
    set process status, show stub."""
    async with async_session() as db:
        # Mark non-selected as REJECTED
        result = await db.execute(
            select(AutomationOpportunity).where(
                AutomationOpportunity.process_id == process_id,
                AutomationOpportunity.status == OpportunityStatus.PROPOSED,
            )
        )
        for opp in result.scalars().all():
            opp.status = OpportunityStatus.REJECTED

        # Count selected
        result = await db.execute(
            select(AutomationOpportunity).where(
                AutomationOpportunity.process_id == process_id,
                AutomationOpportunity.status == OpportunityStatus.SELECTED,
            )
        )
        selected = result.scalars().all()

        process = await db.get(Process, process_id)
        if process:
            process.status = ProcessStatus.READY_FOR_TOBE
        await db.commit()

    # Show stub
    summary = f"✅ Выбрано {len(selected)} точек автоматизации:\n\n"
    for i, opp in enumerate(selected, 1):
        summary += f"{i}. *{opp.title}*\n"

    summary += (
        "\n🚀 Процесс готов к составлению TO-BE.\n\n"
        "_Генерация TO-BE будет доступна в следующем обновлении._"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📋 Составить TO-BE",
            callback_data=f"tobe_{process_id}",
        )
    ]])

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=summary,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
        except Exception:
            pass

    await bot.send_message(
        chat_id=chat_id,
        text=summary,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Legacy handlers (kept for backward compatibility)
# ---------------------------------------------------------------------------

async def send_next_opportunity(chat_id: int, process_id: int, bot) -> None:
    """Legacy: redirect to new multiselect flow."""
    await show_opportunities_multiselect(chat_id, process_id, bot)


async def handle_opportunity_select(
    chat_id: int, opp_id: int, bot
) -> None:
    """Legacy: mark opportunity as selected."""
    process_id = await _set_opp_status(opp_id, OpportunityStatus.SELECTED)
    await bot.send_message(chat_id=chat_id, text="✅ Выбрано!")
    if process_id:
        await send_next_opportunity(chat_id, process_id, bot)


async def handle_opportunity_reject(
    chat_id: int, opp_id: int, bot
) -> None:
    """Legacy: mark opportunity as rejected."""
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
    """Legacy: Show summary of selected opportunities and CTA."""
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
