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


def test_deepseek_adapts_json_schema_without_vllm_extra_body(monkeypatch) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_client, "_client", fake_client)
    monkeypatch.setattr(llm_client.settings, "LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "deepseek-v4-flash")

    llm_client.chat(
        [{"role": "user", "content": "return json"}],
        response_format=json_schema_format(MatchResult),
        enable_thinking=False,
    )

    assert fake_client.chat.completions.kwargs is not None
    assert fake_client.chat.completions.kwargs["model"] == "deepseek-v4-flash"
    assert fake_client.chat.completions.kwargs["response_format"] == {"type": "json_object"}
    assert "extra_body" not in fake_client.chat.completions.kwargs


def test_local_vllm_keeps_json_schema_and_thinking_extra_body(monkeypatch) -> None:
    fake_client = _FakeClient()
    schema = json_schema_format(MatchResult)
    monkeypatch.setattr(llm_client, "_client", fake_client)
    monkeypatch.setattr(llm_client.settings, "LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "qwen3.5:9b")

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
