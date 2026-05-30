"""vLLM lifecycle configuration tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from adacascade.config import Settings

_YAML_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def test_vllm_runtime_settings_load_required_defaults_from_yaml() -> None:
    with _YAML_PATH.open(encoding="utf-8") as handle:
        yaml_defaults = yaml.safe_load(handle)["vllm"]

    assert yaml_defaults == {
        "idle_timeout_seconds": 900,
        "startup_timeout_seconds": 240,
        "shutdown_grace_seconds": 10,
        "health_poll_seconds": 1.0,
        "log_path": "./data/logs/vllm.log",
        "start_command": "bash scripts/start_llm.sh",
    }

    settings = Settings(_env_file=None)

    assert settings.VLLM_IDLE_TIMEOUT_SECONDS == 900
    assert settings.VLLM_STARTUP_TIMEOUT_SECONDS == 240
    assert settings.VLLM_SHUTDOWN_GRACE_SECONDS == 10
    assert settings.VLLM_HEALTH_POLL_SECONDS == 1.0
    assert settings.VLLM_LOG_PATH == "./data/logs/vllm.log"
    assert settings.VLLM_START_COMMAND == "bash scripts/start_llm.sh"


def test_vllm_runtime_settings_allow_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("VLLM_IDLE_TIMEOUT_SECONDS", "1200")
    monkeypatch.setenv("VLLM_LOG_PATH", "/tmp/custom-vllm.log")

    settings = Settings(_env_file=None)

    assert settings.VLLM_IDLE_TIMEOUT_SECONDS == 1200
    assert settings.VLLM_LOG_PATH == "/tmp/custom-vllm.log"


def test_vllm_runtime_settings_allow_constructor_overrides() -> None:
    settings = Settings(
        _env_file=None,
        VLLM_STARTUP_TIMEOUT_SECONDS=321,
        VLLM_HEALTH_POLL_SECONDS=2.5,
        VLLM_START_COMMAND="python -m fake_vllm",
    )

    assert settings.VLLM_STARTUP_TIMEOUT_SECONDS == 321
    assert settings.VLLM_HEALTH_POLL_SECONDS == 2.5
    assert settings.VLLM_START_COMMAND == "python -m fake_vllm"
