"""LLM client local runtime request tracking tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from adacascade import llm_client


class _FakeCompletions:
    def __init__(self, manager: _FakeManager) -> None:
        self.manager = manager
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> object:
        self.manager.events.append("create")
        self.kwargs = kwargs
        return object()


class _FakeChat:
    def __init__(self, manager: _FakeManager) -> None:
        self.completions = _FakeCompletions(manager)


class _FakeClient:
    def __init__(self, manager: _FakeManager) -> None:
        self.chat = _FakeChat(manager)


class _FakeManager:
    def __init__(self) -> None:
        self.backends: list[str] = []
        self.events: list[str] = []
        self.active_local_count = 0
        self.max_active_local_count = 0
        self.ensure_ready_sync_calls = 0
        self.ensure_ready_calls = 0

    def ensure_ready_sync(self) -> dict[str, object]:
        self.events.append("ensure_ready_sync")
        self.ensure_ready_sync_calls += 1
        return {"local_status": "ready", "local_ready": True, "local_last_error": None}

    async def ensure_ready(self) -> dict[str, object]:
        self.events.append("ensure_ready")
        self.ensure_ready_calls += 1
        return {"local_status": "ready", "local_ready": True, "local_last_error": None}

    @contextmanager
    def track_request(self, backend: str) -> Iterator[None]:
        self.events.append(f"enter:{backend}")
        self.backends.append(backend)
        if backend == "local":
            self.active_local_count += 1
            self.max_active_local_count = max(
                self.max_active_local_count, self.active_local_count
            )
        try:
            yield
        finally:
            if backend == "local":
                self.active_local_count -= 1
            self.events.append(f"exit:{backend}")


def _configure_chat(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: str,
    manager: _FakeManager,
) -> _FakeClient:
    fake_client = _FakeClient(manager)
    config = llm_client.llm_runtime.LlmRequestConfig(
        backend=backend,  # type: ignore[arg-type]
        base_url=(
            "http://localhost:8000/v1"
            if backend == "local"
            else "https://api.deepseek.com"
        ),
        api_key="EMPTY" if backend == "local" else "TEST_API_TOKEN",
        model="qwen3.5:9b" if backend == "local" else "deepseek-v4-flash",
        timeout=30,
    )
    monkeypatch.setattr(llm_client.llm_runtime, "get_request_config", lambda: config)
    monkeypatch.setattr(llm_client, "_client_for_config", lambda _config: fake_client)
    monkeypatch.setattr(llm_client.local_llm_runtime, "get_manager", lambda: manager)
    return fake_client


def test_chat_tracks_local_backend_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _FakeManager()
    _configure_chat(monkeypatch, backend="local", manager=manager)

    llm_client.chat([{"role": "user", "content": "return json"}])

    assert manager.backends == ["local"]
    assert manager.max_active_local_count == 1
    assert manager.active_local_count == 0
    assert manager.events == ["ensure_ready_sync", "enter:local", "create", "exit:local"]


def test_chat_tracks_api_backend_without_local_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeManager()
    _configure_chat(monkeypatch, backend="api", manager=manager)

    llm_client.chat([{"role": "user", "content": "return json"}])

    assert manager.backends == ["api"]
    assert manager.max_active_local_count == 0
    assert manager.active_local_count == 0
    assert manager.events == ["enter:api", "create", "exit:api"]


def test_chat_ensures_local_runtime_ready_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeManager()
    _configure_chat(monkeypatch, backend="local", manager=manager)

    llm_client.chat([{"role": "user", "content": "return json"}])

    assert manager.ensure_ready_sync_calls == 1
    assert manager.ensure_ready_calls == 0
    assert manager.events.index("ensure_ready_sync") < manager.events.index("create")


@pytest.mark.anyio
async def test_chat_async_ensures_local_runtime_ready_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeManager()
    _configure_chat(monkeypatch, backend="local", manager=manager)

    await llm_client.chat_async([{"role": "user", "content": "return json"}])

    assert manager.ensure_ready_sync_calls == 0
    assert manager.ensure_ready_calls == 1
    assert manager.backends == ["local"]
    assert manager.max_active_local_count == 1
    assert manager.active_local_count == 0
    assert manager.events == ["ensure_ready", "enter:local", "create", "exit:local"]
