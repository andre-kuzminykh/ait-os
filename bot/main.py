"""Main entry point for the Andre AI Telegram bot."""

from __future__ import annotations

import logging

from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN
from bot.database import init_db
from bot.handlers.callbacks import callback_handler, get_chat_context
from bot.handlers.clarification import handle_gap_answer
from bot.handlers.interview import (
    handle_document,
    handle_text_message,
    handle_voice_message,
)
from bot.handlers.start import cmd_start, handle_new_process_name

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _text_router(update, context):
    """Route text messages: process name, gap answer, or general interview input."""
    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)

    # 1. Awaiting process name (user clicked "+")
    if ctx and ctx.get("awaiting_process_name"):
        text = (update.message.text or "").strip()
        if text:
            tg_user_id = update.effective_user.id if update.effective_user else None
            await handle_new_process_name(
                context.bot, chat_id, text, tg_user_id,
                update.message.message_id,
            )
        return

    # 2. Pending gap answer
    if ctx and ctx.get("pending_gap_id"):
        gap_id = ctx.pop("pending_gap_id")
        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(chat_id, ctx)
        await handle_gap_answer(update, gap_id, update.message.text)
        return

    # 3. General interview input
    await handle_text_message(update, context)


async def _voice_router(update, context):
    """Route voice/audio messages: gap answer or general interview input."""
    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)

    if ctx and ctx.get("pending_gap_id"):
        # Transcribe first, then treat as gap answer
        from bot.services.transcription import transcribe_telegram_voice
        voice = update.message.voice or update.message.audio
        if voice:
            transcript = await transcribe_telegram_voice(context.bot, voice.file_id)
            if transcript:
                gap_id = ctx.pop("pending_gap_id")
                from bot.handlers.callbacks import save_chat_context
                await save_chat_context(chat_id, ctx)
                await handle_gap_answer(update, gap_id, transcript)
                return

    await handle_voice_message(update, context)


async def post_init(application):
    """Initialize database and set up bot menu after application starts."""
    await init_db()
    logger.info("Database initialized")

    # Set up burger menu with single "Процессы" command
    await application.bot.set_my_commands([
        BotCommand("start", "Процессы"),
    ])
    logger.info("Bot menu commands set")


def main():
    """Build and run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Exiting.")
        return

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))

    # Callback query handler (inline buttons)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Message handlers
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _text_router)
    )
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, _voice_router)
    )
    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_document)
    )

    logger.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
