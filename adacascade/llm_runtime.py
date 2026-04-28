"""Process-local runtime LLM backend selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict, cast

from adacascade.config import settings

LlmBackend = Literal["local", "api"]


class RuntimeInfo(TypedDict):
    backend: LlmBackend
    base_url: str
    model: str
    api_key_configured: bool


@dataclass(frozen=True)
class LlmRequestConfig:
    backend: LlmBackend
    base_url: str
    api_key: str
    model: str
    timeout: int


_active_backend: LlmBackend = "local"


def _backend_config(backend: LlmBackend) -> LlmRequestConfig:
    if backend == "local":
        return LlmRequestConfig(
            backend="local",
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
            model="qwen3.5:9b",
            timeout=settings.LLM_TIMEOUT,
        )
    return LlmRequestConfig(
        backend="api",
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or "EMPTY",
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
    )


def _safe_info(config: LlmRequestConfig) -> RuntimeInfo:
    return {
        "backend": config.backend,
        "base_url": config.base_url,
        "model": config.model,
        "api_key_configured": config.backend == "local"
        or bool(config.api_key and config.api_key != "EMPTY"),
    }


def get_active_backend() -> LlmBackend:
    """Return the process-local active LLM backend."""
    return _active_backend


def get_request_config() -> LlmRequestConfig:
    """Return the active backend request configuration."""
    return _backend_config(_active_backend)


def get_runtime_info() -> RuntimeInfo:
    """Return safe runtime metadata for API responses."""
    return _safe_info(get_request_config())


def set_active_backend(backend: str) -> RuntimeInfo:
    """Switch the process-local LLM backend and return safe metadata."""
    if backend not in {"local", "api"}:
        raise ValueError(f"Unsupported LLM backend: {backend}")

    global _active_backend
    _active_backend = cast(LlmBackend, backend)
    return get_runtime_info()
