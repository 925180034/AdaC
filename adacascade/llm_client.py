"""OpenAI-compatible LLM client wrapper.

Supports any backend that implements the OpenAI API (vLLM, DeepSeek, Qwen cloud).
Switch backends by changing LLM_BASE_URL in .env — zero business logic changes.
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import urlparse

from openai import OpenAI
from openai.types.chat import ChatCompletion

from adacascade import llm_runtime
from adacascade.config import settings


def _client_for_config(config: llm_runtime.LlmRequestConfig) -> OpenAI:
    """Create an OpenAI-compatible client for an immutable request config.

    Args:
        config: Active runtime LLM backend configuration.

    Returns:
        OpenAI-compatible client scoped to the request configuration.
    """
    return OpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout,
    )


def _is_deepseek_backend(base_url: str) -> bool:
    return urlparse(base_url).hostname == "api.deepseek.com"


def _adapt_response_format(
    response_format: dict[str, Any] | None,
    base_url: str,
) -> dict[str, Any] | None:
    if (
        _is_deepseek_backend(base_url)
        and response_format
        and response_format.get("type") == "json_schema"
    ):
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
    runtime_config = llm_runtime.get_request_config()
    client = _client_for_config(runtime_config)
    extra_body: dict[str, Any] = kwargs.pop("extra_body", {})
    if not _is_deepseek_backend(runtime_config.base_url):
        extra_body.setdefault(
            "chat_template_kwargs", {"enable_thinking": enable_thinking}
        )

    max_tok = max_tokens or cast(int, settings.llm_cfg.get("max_tokens", 512))
    request_kwargs: dict[str, Any] = {
        "model": model or runtime_config.model,
        "messages": messages,
        "temperature": temperature,
        "response_format": _adapt_response_format(
            response_format, runtime_config.base_url
        ),
        "max_tokens": max_tok,
        **kwargs,
    }
    if extra_body:
        request_kwargs["extra_body"] = extra_body

    resp = client.chat.completions.create(  # type: ignore[call-overload]
        **request_kwargs,
    )
    return cast(ChatCompletion, resp)
