"""Progress message utilities for clean, step-by-step UX feedback."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def send_progress(
    bot, chat_id: int, text: str, message_id: int | None = None,
    parse_mode: str | None = None,
) -> int:
    """Send or edit a progress message. Returns message_id."""
    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
            )
            return message_id
        except Exception:
            logger.debug("Could not edit message %s, sending new", message_id)

    msg = await bot.send_message(
        chat_id=chat_id, text=text, parse_mode=parse_mode,
    )
    return msg.message_id


async def typewriter_send(
    bot,
    chat_id: int,
    full_text: str,
    prefix: str = "",
    steps: int = 4,
    message_id: int | None = None,
) -> int:
    """Send text with typewriter effect (progressive reveal via edits)."""
    if not full_text:
        return await send_progress(bot, chat_id, prefix or "...", message_id)

    display = full_text[:500]
    chunk_size = max(1, len(display) // steps)

    mid = await send_progress(
        bot, chat_id, f"{prefix}{display[:chunk_size]}▌", message_id,
    )

    for i in range(2, steps + 1):
        end = min(i * chunk_size, len(display))
        cursor = "▌" if end < len(display) else ""
        mid = await send_progress(
            bot, chat_id, f"{prefix}{display[:end]}{cursor}", mid,
        )
        if end < len(display):
            await asyncio.sleep(0.3)

    return mid


async def delete_messages(bot, chat_id: int, message_ids: list[int]) -> None:
    """Delete multiple messages, ignoring errors for already-deleted ones."""
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            logger.debug("Could not delete message %s in chat %s", mid, chat_id)
