"""LLM client wrapper using Anthropic Claude API."""

import anthropic

from bot.config import ANTHROPIC_API_KEY, LLM_MAX_TOKENS, LLM_MODEL

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
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
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
