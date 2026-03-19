"""LLM client wrapper using OpenAI API."""

import logging

from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, LLM_MAX_TOKENS, LLM_MODEL

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def chat(
    system_prompt: str,
    user_message: str,
    *,
    model: str = LLM_MODEL,
    max_tokens: int = LLM_MAX_TOKENS,
) -> str:
    """Send a single-turn message and return assistant text."""
    client = get_client()

    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content or ""
