"""Voice / audio transcription service."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import aiohttp

from bot.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


async def transcribe_file(file_path: str | Path) -> str:
    """Transcribe an audio file using OpenAI Whisper API.

    Falls back to empty string if API key is not configured.
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — transcription unavailable")
        return ""

    file_path = Path(file_path)
    data = aiohttp.FormData()
    data.add_field("model", "whisper-1")
    data.add_field("language", "ru")
    data.add_field(
        "file",
        open(file_path, "rb"),
        filename=file_path.name,
        content_type="audio/ogg",
    )

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(WHISPER_URL, data=data, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error("Whisper API error %s: %s", resp.status, text)
                return ""
            result = await resp.json()
            return result.get("text", "")


async def transcribe_telegram_voice(bot, file_id: str) -> str:
    """Download a Telegram voice/audio file and transcribe it."""
    tg_file = await bot.get_file(file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    await tg_file.download_to_drive(tmp_path)

    try:
        text = await transcribe_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return text
