"""Runtime LLM API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token", "X-Tenant-Id": "default"}


@pytest.fixture()
def client() -> TestClient:
    mock_qdrant = MagicMock()
    raw_qdrant_mock = AsyncMock()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch("adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)),
    ):
        from adacascade import llm_runtime
        from adacascade.api.app import app

        llm_runtime.set_active_backend("local")
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
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
    assert "api_key" not in body


def test_runtime_llm_put_switches_backend(client: TestClient) -> None:
    switched = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "api"})
    current = client.get("/runtime/llm", headers=AUTH_HEADERS)

    assert switched.status_code == 200
    assert switched.json()["backend"] == "api"
    assert current.json()["backend"] == "api"
    assert "api_key" not in switched.text


def test_runtime_llm_put_rejects_invalid_backend(client: TestClient) -> None:
    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "ollama"})

    assert resp.status_code == 422
