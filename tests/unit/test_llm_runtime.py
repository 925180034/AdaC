"""Runtime LLM backend configuration tests."""

from __future__ import annotations

import pytest

from adacascade import llm_runtime


def reset_runtime() -> None:
    llm_runtime.set_active_backend("local")


def test_default_backend_is_local() -> None:
    reset_runtime()

    info = llm_runtime.get_runtime_info()

    assert info["backend"] == "local"
    assert info["api_key_configured"] is True
    assert "api_key" not in info


def test_switches_to_api_backend_without_exposing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime()
    monkeypatch.setattr(llm_runtime.settings, "LLM_API_KEY", "sk-test-secret")
    monkeypatch.setattr(llm_runtime.settings, "LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(llm_runtime.settings, "LLM_MODEL", "deepseek-v4-flash")

    info = llm_runtime.set_active_backend("api")

    assert info == {
        "backend": "api",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_configured": True,
    }
    assert "sk-test-secret" not in str(info)


def test_rejects_unknown_backend() -> None:
    reset_runtime()

    with pytest.raises(ValueError, match="Unsupported LLM backend"):
        llm_runtime.set_active_backend("ollama")


def test_request_config_tracks_active_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime()
    monkeypatch.setattr(llm_runtime.settings, "LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(llm_runtime.settings, "LLM_API_KEY", "sk-test-secret")
    monkeypatch.setattr(llm_runtime.settings, "LLM_MODEL", "deepseek-v4-flash")

    llm_runtime.set_active_backend("api")
    api_config = llm_runtime.get_request_config()

    assert api_config.backend == "api"
    assert api_config.base_url == "https://api.deepseek.com"
    assert api_config.api_key == "sk-test-secret"
    assert api_config.model == "deepseek-v4-flash"

    llm_runtime.set_active_backend("local")
    local_config = llm_runtime.get_request_config()

    assert local_config.backend == "local"
    assert local_config.base_url == llm_runtime.settings.LLM_LOCAL_BASE_URL
    assert local_config.api_key == "EMPTY"
    assert local_config.model == llm_runtime.settings.LLM_LOCAL_MODEL


def test_local_backend_uses_local_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime()
    monkeypatch.setattr(llm_runtime.settings, "LLM_LOCAL_BASE_URL", "http://127.0.0.1:9000/v1")
    monkeypatch.setattr(llm_runtime.settings, "LLM_LOCAL_MODEL", "qwen-local-test")
    monkeypatch.setattr(llm_runtime.settings, "LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(llm_runtime.settings, "LLM_MODEL", "deepseek-v4-flash")

    config = llm_runtime.get_request_config()

    assert config.backend == "local"
    assert config.base_url == "http://127.0.0.1:9000/v1"
    assert config.model == "qwen-local-test"
