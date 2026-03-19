"""LLM client wrapper using Anthropic Claude API with extended thinking."""

import logging

import anthropic

from bot.config import ANTHROPIC_API_KEY, LLM_MAX_TOKENS, LLM_MODEL, LLM_THINKING_BUDGET

logger = logging.getLogger(__name__)

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
    use_thinking: bool = True,
    thinking_budget: int = LLM_THINKING_BUDGET,
) -> str:
    """Send a single-turn message and return assistant text.

    Uses extended thinking (Claude's reasoning mode) by default for
    deeper analysis of business processes.
    """
    client = get_client()

    if use_thinking:
        # Extended thinking mode — system prompt goes into user message
        # because extended thinking doesn't support system parameter
        combined_message = f"{system_prompt}\n\n---\n\n{user_message}"
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens + thinking_budget,
            thinking={
                "type": "enabled",
                "budget_tokens": thinking_budget,
            },
            messages=[{"role": "user", "content": combined_message}],
        )
    else:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

    # Extract text from response, skipping thinking blocks
    for block in response.content:
        if block.type == "text":
            return block.text

    return ""
