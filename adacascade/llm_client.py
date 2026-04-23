"""OpenAI-compatible LLM client wrapper.

Supports any backend that implements the OpenAI API (vLLM, DeepSeek, Qwen cloud).
Switch backends by changing LLM_BASE_URL in .env — zero business logic changes.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion

from adacascade.config import settings

_client = OpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY or "EMPTY",
    timeout=settings.LLM_TIMEOUT,
)


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.0,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    enable_thinking: bool = False,
    **kwargs: Any,
) -> ChatCompletion:
    """Send a chat completion request.

    Args:
        messages: OpenAI-format message list.
        model: Override the default LLM model.
        temperature: Sampling temperature (0.0 for deterministic).
        response_format: JSON Schema constrained decoding config.
        max_tokens: Max output tokens.
        enable_thinking: Qwen3-specific thinking mode (always False for
            classification tasks per CLAUDE.md §9 pitfalls).
        **kwargs: Extra parameters forwarded to the API.

    Returns:
        Raw ChatCompletion response.
    """
    extra_body: dict[str, Any] = kwargs.pop("extra_body", {})
    extra_body.setdefault(
        "chat_template_kwargs", {"enable_thinking": enable_thinking}
    )

    return _client.chat.completions.create(
        model=model or settings.LLM_MODEL,
        messages=messages,
        temperature=temperature,
        response_format=response_format,
        max_tokens=max_tokens or settings.llm_cfg.get("max_tokens", 512),
        extra_body=extra_body,
        **kwargs,
    )
