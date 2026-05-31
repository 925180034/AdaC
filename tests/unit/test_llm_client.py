"""LLM client backend adaptation tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from adacascade import llm_client
from adacascade.llm_schemas import MatchResult, json_schema_format


class _FakeCompletions:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return object()


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


class _FakeManager:
    def __init__(self) -> None:
        self.ensure_ready_sync_calls = 0
        self.ensure_ready_calls = 0
        self.backends: list[str] = []
        self.fail_async_ensure_ready = True

    def ensure_ready_sync(self) -> dict[str, object]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Local LLM sync readiness cannot run inside an active event loop; "
                "use adacascade.llm_client.chat_async() instead."
            )
        self.ensure_ready_sync_calls += 1
        return {"local_status": "ready", "local_ready": True, "local_last_error": None}

    async def ensure_ready(self) -> dict[str, object]:
        self.ensure_ready_calls += 1
        if self.fail_async_ensure_ready:
            raise AssertionError("chat must use ensure_ready_sync for local backend")
        return {"local_status": "ready", "local_ready": True, "local_last_error": None}

    def track_request(self, backend: str):
        self.backends.append(backend)

        class _Tracker:
            def __enter__(self_inner) -> None:
                return None

            def __exit__(self_inner, exc_type, exc, tb) -> None:
                return None

        return _Tracker()


@pytest.fixture(autouse=True)
def fake_runtime_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeManager]:
    manager = _FakeManager()
    monkeypatch.setattr(llm_client.local_llm_runtime, "get_manager", lambda: manager)
    yield manager


def test_chat_uses_client_for_runtime_config_each_call(monkeypatch) -> None:
    fake_client = _FakeClient()
    config = llm_client.llm_runtime.LlmRequestConfig(
        backend="api",
        base_url="https://api.deepseek.com",
        api_key="TEST_API_TOKEN",
        model="deepseek-v4-flash",
        timeout=60,
    )
    received_configs: list[llm_client.llm_runtime.LlmRequestConfig] = []

    def fake_client_for_config(
        runtime_config: llm_client.llm_runtime.LlmRequestConfig,
    ) -> _FakeClient:
        received_configs.append(runtime_config)
        return fake_client

    monkeypatch.setattr(llm_client.llm_runtime, "get_request_config", lambda: config)
    monkeypatch.setattr(llm_client, "_client_for_config", fake_client_for_config)

    llm_client.chat([{"role": "user", "content": "return json"}])

    assert received_configs == [config]
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "deepseek-v4-flash"


def test_deepseek_adapts_json_schema_without_vllm_extra_body(monkeypatch) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_client, "_client_for_config", lambda _config: fake_client)
    monkeypatch.setattr(
        llm_client.llm_runtime,
        "get_request_config",
        lambda: llm_client.llm_runtime.LlmRequestConfig(
            backend="api",
            base_url="https://api.deepseek.com",
            api_key="TEST_API_TOKEN",
            model="deepseek-v4-flash",
            timeout=60,
        ),
    )

    llm_client.chat(
        [{"role": "user", "content": "return json"}],
        response_format=json_schema_format(MatchResult),
        enable_thinking=False,
    )

    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "deepseek-v4-flash"
    assert fake_client.chat.completions.kwargs["response_format"] == {
        "type": "json_object"
    }
    assert "extra_body" not in fake_client.chat.completions.kwargs


@pytest.mark.anyio
async def test_chat_async_uses_async_local_readiness_and_tracks_request(
    monkeypatch: pytest.MonkeyPatch,
    fake_runtime_manager: _FakeManager,
) -> None:
    fake_client = _FakeClient()
    fake_runtime_manager.fail_async_ensure_ready = False
    monkeypatch.setattr(llm_client, "_client_for_config", lambda _config: fake_client)
    monkeypatch.setattr(
        llm_client.llm_runtime,
        "get_request_config",
        lambda: llm_client.llm_runtime.LlmRequestConfig(
            backend="local",
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
            model="qwen3.5:9b",
            timeout=30,
        ),
    )

    await llm_client.chat_async([{"role": "user", "content": "return json"}])

    assert fake_runtime_manager.ensure_ready_sync_calls == 0
    assert fake_runtime_manager.ensure_ready_calls == 1
    assert fake_runtime_manager.backends == ["local"]
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "qwen3.5:9b"


@pytest.mark.anyio
async def test_chat_local_from_running_loop_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_client, "_client_for_config", lambda _config: fake_client)
    monkeypatch.setattr(
        llm_client.llm_runtime,
        "get_request_config",
        lambda: llm_client.llm_runtime.LlmRequestConfig(
            backend="local",
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
            model="qwen3.5:9b",
            timeout=30,
        ),
    )

    with pytest.raises(RuntimeError, match="chat_async"):
        llm_client.chat([{"role": "user", "content": "return json"}])



def test_local_vllm_keeps_json_schema_and_thinking_extra_body(monkeypatch) -> None:
    fake_client = _FakeClient()
    fake_manager = _FakeManager()
    schema = json_schema_format(MatchResult)
    monkeypatch.setattr(llm_client, "_client_for_config", lambda _config: fake_client)
    monkeypatch.setattr(
        llm_client.llm_runtime,
        "get_request_config",
        lambda: llm_client.llm_runtime.LlmRequestConfig(
            backend="local",
            base_url="http://localhost:8000/v1",
            api_key="EMPTY",
            model="qwen3.5:9b",
            timeout=30,
        ),
    )
    monkeypatch.setattr(llm_client.local_llm_runtime, "get_manager", lambda: fake_manager)

    llm_client.chat(
        [{"role": "user", "content": "return json"}],
        response_format=schema,
        enable_thinking=False,
    )

    assert fake_manager.ensure_ready_sync_calls == 1
    assert fake_manager.ensure_ready_calls == 0
    assert fake_manager.backends == ["local"]
    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["response_format"] == schema
    assert fake_client.chat.completions.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
