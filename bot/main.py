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
    """Route text messages: process name, clarification answer, gap answer, or interview."""
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

    # 2. Active clarification Q&A — user answers directly
    if ctx and ctx.get("clarification_active"):
        text = (update.message.text or "").strip()
        if text:
            from bot.handlers.clarification import handle_clarification_answer
            await handle_clarification_answer(update, text)
        return

    # 3. Pending gap answer (legacy flow)
    if ctx and ctx.get("pending_gap_id"):
        gap_id = ctx.pop("pending_gap_id")
        from bot.handlers.callbacks import save_chat_context
        await save_chat_context(chat_id, ctx)
        await handle_gap_answer(update, gap_id, update.message.text)
        return

    # 4. General interview input
    await handle_text_message(update, context)


async def _voice_router(update, context):
    """Route voice/audio messages: clarification answer, gap answer, or interview."""
    chat_id = update.effective_chat.id
    ctx = await get_chat_context(chat_id)

    # 1. Active clarification Q&A — transcribe and answer
    if ctx and ctx.get("clarification_active"):
        from bot.services.transcription import transcribe_telegram_voice
        voice = update.message.voice or update.message.audio
        if voice:
            transcript = await transcribe_telegram_voice(context.bot, voice.file_id)
            if transcript:
                from bot.handlers.clarification import handle_clarification_answer
                await handle_clarification_answer(update, transcript)
                return

    # 2. Pending gap answer (legacy flow)
    if ctx and ctx.get("pending_gap_id"):
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

    # 3. General interview input
    await handle_voice_message(update, context)


async def post_init(application):
    """Initialize database, start pages HTTP server, and set up bot menu."""
    await init_db()
    logger.info("Database initialized")

    # Start HTTP server for published pages
    from bot.web import start_web_server
    application.bot_data["web_runner"] = await start_web_server()

    # Set up burger menu with single "Процессы" command
    await application.bot.set_my_commands([
        BotCommand("start", "Процессы"),
    ])
    logger.info("Bot menu commands set")


async def post_shutdown(application):
    """Clean up the HTTP server on bot shutdown."""
    runner = application.bot_data.get("web_runner")
    if runner:
        await runner.cleanup()
        logger.info("Pages HTTP server stopped")


def main():
    """Build and run the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Exiting.")
        return

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
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
