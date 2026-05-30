"""Runtime LLM API tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token", "X-Tenant-Id": "default"}


class FakeLocalRuntimeManager:
    def __init__(self) -> None:
        self.ensure_ready_calls = 0
        self.stop_managed_calls = 0
        self.raise_on_ensure: Exception | None = None
        self.snapshot_payload: dict[str, object] = {
            "local_status": "stopped",
            "local_ready": False,
            "local_last_error": None,
        }

    def snapshot(self) -> dict[str, object]:
        return dict(self.snapshot_payload)

    async def ensure_ready(self) -> dict[str, object]:
        self.ensure_ready_calls += 1
        if self.raise_on_ensure is not None:
            self.snapshot_payload = {
                "local_status": "error",
                "local_ready": False,
                "local_last_error": str(self.raise_on_ensure),
            }
            raise self.raise_on_ensure
        self.snapshot_payload = {
            "local_status": "ready",
            "local_ready": True,
            "local_last_error": None,
        }
        return self.snapshot()

    async def stop_managed(self) -> dict[str, object]:
        self.stop_managed_calls += 1
        self.snapshot_payload = {
            "local_status": "stopped",
            "local_ready": False,
            "local_last_error": None,
        }
        return self.snapshot()


@pytest.fixture()
def client() -> TestClient:
    mock_qdrant = MagicMock()
    raw_qdrant_mock = AsyncMock()
    fake_manager = FakeLocalRuntimeManager()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch(
            "adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)
        ),
        patch("adacascade.local_llm_runtime.get_manager", return_value=fake_manager),
    ):
        from adacascade import llm_runtime
        from adacascade.api.app import app

        llm_runtime.set_active_backend("local")
        app.state.fake_local_runtime_manager = fake_manager
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c
        finally:
            llm_runtime.set_active_backend("local")


def test_runtime_llm_requires_auth(client: TestClient) -> None:
    resp = client.get("/runtime/llm")

    assert resp.status_code == 401


def test_runtime_llm_get_returns_safe_metadata(client: TestClient) -> None:
    resp = client.get("/runtime/llm", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "local"
    assert body["model"] == "qwen3.5:9b"
    assert body["local_status"] == "stopped"
    assert body["local_ready"] is False
    assert body["local_last_error"] is None
    assert "api_key" not in body
    assert "EMPTY" not in resp.text


def test_runtime_llm_put_local_waits_until_local_runtime_ready(
    client: TestClient,
) -> None:
    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "local"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "local"
    assert body["local_status"] == "ready"
    assert body["local_ready"] is True
    assert body["local_last_error"] is None
    assert client.app.state.fake_local_runtime_manager.ensure_ready_calls == 1
    assert '"api_key"' not in resp.text
    assert "EMPTY" not in resp.text


def test_runtime_llm_put_api_stops_managed_local_runtime(client: TestClient) -> None:
    switched = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "api"})
    current = client.get("/runtime/llm", headers=AUTH_HEADERS)

    assert switched.status_code == 200
    body = switched.json()
    assert body["backend"] == "api"
    assert body["local_status"] == "stopped"
    assert body["local_ready"] is False
    assert current.json()["backend"] == "api"
    assert client.app.state.fake_local_runtime_manager.stop_managed_calls == 1
    assert '"api_key"' not in switched.text
    assert "EMPTY" not in switched.text


def test_runtime_llm_put_local_failure_falls_back_to_api_safely(
    client: TestClient,
) -> None:
    from adacascade.local_llm_runtime import LocalRuntimeError

    manager = client.app.state.fake_local_runtime_manager
    manager.raise_on_ensure = LocalRuntimeError("Local vLLM startup timed out")

    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "local"})
    current = client.get("/runtime/llm", headers=AUTH_HEADERS)

    assert resp.status_code == 503
    assert resp.json() == {"detail": "Local vLLM startup timed out"}
    assert current.json()["backend"] == "api"
    assert manager.ensure_ready_calls == 1
    assert '"api_key"' not in resp.text
    assert "EMPTY" not in resp.text


def test_runtime_llm_put_rejects_invalid_backend(client: TestClient) -> None:
    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "ollama"})

    assert resp.status_code == 422


@pytest.mark.anyio
async def test_runtime_llm_put_serializes_overlapping_backend_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade import llm_runtime
    from adacascade.api.routes import runtime

    class ControlledLocalRuntimeManager:
        def __init__(self) -> None:
            self.ensure_entered = asyncio.Event()
            self.allow_ensure = asyncio.Event()
            self.stop_entered = asyncio.Event()
            self.events: list[str] = []
            self.snapshot_payload: dict[str, object] = {
                "local_status": "stopped",
                "local_ready": False,
                "local_last_error": None,
            }

        def snapshot(self) -> dict[str, object]:
            return dict(self.snapshot_payload)

        async def ensure_ready(self) -> dict[str, object]:
            self.events.append("ensure:start")
            self.ensure_entered.set()
            await self.allow_ensure.wait()
            self.snapshot_payload = {
                "local_status": "ready",
                "local_ready": True,
                "local_last_error": None,
            }
            self.events.append("ensure:end")
            return self.snapshot()

        async def stop_managed(self) -> dict[str, object]:
            self.events.append("stop:start")
            self.stop_entered.set()
            self.snapshot_payload = {
                "local_status": "stopped",
                "local_ready": False,
                "local_last_error": None,
            }
            self.events.append("stop:end")
            return self.snapshot()

    manager = ControlledLocalRuntimeManager()
    monkeypatch.setattr(runtime.local_llm_runtime, "get_manager", lambda: manager)
    llm_runtime.set_active_backend("api")

    local_task = asyncio.create_task(
        runtime.update_llm_runtime(runtime.LlmRuntimeUpdate(backend="local"))
    )
    await manager.ensure_entered.wait()

    api_task = asyncio.create_task(
        runtime.update_llm_runtime(runtime.LlmRuntimeUpdate(backend="api"))
    )
    await asyncio.sleep(0)

    assert manager.events == ["ensure:start"]
    assert manager.stop_entered.is_set() is False

    manager.allow_ensure.set()
    local_response, api_response = await asyncio.gather(local_task, api_task)

    assert manager.events == ["ensure:start", "ensure:end", "stop:start", "stop:end"]
    assert local_response.backend == "local"
    assert local_response.local_status == "ready"
    assert api_response.backend == "api"
    assert api_response.local_status == "stopped"
    assert llm_runtime.get_active_backend() == "api"
