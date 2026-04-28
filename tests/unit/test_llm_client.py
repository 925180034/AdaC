"""LLM client backend adaptation tests."""

from __future__ import annotations

from typing import Any

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


def test_local_vllm_keeps_json_schema_and_thinking_extra_body(monkeypatch) -> None:
    fake_client = _FakeClient()
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

    llm_client.chat(
        [{"role": "user", "content": "return json"}],
        response_format=schema,
        enable_thinking=False,
    )

    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["response_format"] == schema
    assert fake_client.chat.completions.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
