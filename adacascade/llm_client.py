"""OpenAI-compatible LLM client wrapper.

Supports any backend that implements the OpenAI API (vLLM, DeepSeek, Qwen cloud).
Switch backends by changing LLM_BASE_URL in .env — zero business logic changes.
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlparse

from openai import OpenAI
from openai.types.chat import ChatCompletion

from adacascade.config import settings

_client = OpenAI(
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY or "EMPTY",
    timeout=settings.LLM_TIMEOUT,
)


def _is_deepseek_backend() -> bool:
    return urlparse(settings.LLM_BASE_URL).netloc.endswith("api.deepseek.com")


def _adapt_response_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    if _is_deepseek_backend() and response_format and response_format.get("type") == "json_schema":
        return {"type": "json_object"}
    return response_format


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
    if not _is_deepseek_backend():
        extra_body.setdefault("chat_template_kwargs", {"enable_thinking": enable_thinking})

    max_tok = max_tokens or cast(int, settings.llm_cfg.get("max_tokens", 512))
    request_kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": _adapt_response_format(response_format),
        "max_tokens": max_tok,
        **kwargs,
    }
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    resp = _client.chat.completions.create(  # type: ignore[call-overload]
        **request_kwargs,
    )
    return cast(ChatCompletion, resp)
