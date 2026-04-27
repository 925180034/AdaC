"""M1 integration tests — POST /tables → status tracking.

Relies on conftest.py for env var setup before adacascade import.
Mocks Qdrant (AsyncMock) and SBERT so tests run without GPU or external services.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


def _make_mock_qdrant() -> MagicMock:
    """AdacQdrantClient mock with awaitable methods."""
    m = MagicMock()
    m.upsert_table = AsyncMock()
    m.upsert_columns = AsyncMock()
    m.delete_table = AsyncMock()
    m.update_status = AsyncMock()
    m.search_tables = AsyncMock(return_value=[])
    m.search_columns = AsyncMock(return_value=[])
    return m


def _make_mock_sbert() -> MagicMock:
    m = MagicMock()
    m.encode.side_effect = lambda texts, **kw: np.zeros((len(texts), 384))
    return m


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Module-scoped TestClient — env vars set in conftest before import."""
    mock_qdrant = _make_mock_qdrant()
    mock_sbert = _make_mock_sbert()

    raw_qdrant_mock = AsyncMock()  # makes .close() awaitable

    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch("adacascade.agents.profiling._get_sbert", return_value=mock_sbert),
    ):
        from adacascade.api.app import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture(scope="module")
def sample_csv() -> bytes:
    df = pd.DataFrame(
        {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35]}
    )
    return df.to_csv(index=False).encode()


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_csv_returns_202(client: TestClient, sample_csv: bytes) -> None:
    resp = client.post(
        "/tables",
        data={"table_name": "test_table", "source_system": "upload"},
        files={"file": ("test.csv", io.BytesIO(sample_csv), "text/csv")},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "table_id" in body
    assert body["status"] in ("INGESTED", "REJECTED")


def test_get_table_after_upload(client: TestClient, sample_csv: bytes) -> None:
    csv_bytes = (
        pd.DataFrame({"col_a": [10, 20], "col_b": ["x", "y"]})
        .to_csv(index=False)
        .encode()
    )
    upload_resp = client.post(
        "/tables",
        data={"table_name": "status_test"},
        files={"file": ("status_test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert upload_resp.status_code == 202, upload_resp.text
    table_id = upload_resp.json()["table_id"]

    get_resp = client.get(f"/tables/{table_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["table_id"] == table_id
    assert body["status"] in ("INGESTED", "PROFILING", "READY", "REJECTED")


def test_list_tables_returns_200(client: TestClient) -> None:
    resp = client.get("/tables")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert "total" in body


def test_get_nonexistent_table_returns_404(client: TestClient) -> None:
    resp = client.get("/tables/does-not-exist-00000")
    assert resp.status_code == 404


def test_delete_table_returns_archived(client: TestClient, sample_csv: bytes) -> None:
    csv_bytes = pd.DataFrame({"x": [1], "y": ["a"]}).to_csv(index=False).encode()
    upload_resp = client.post(
        "/tables",
        data={"table_name": "delete_test"},
        files={"file": ("delete_test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert upload_resp.status_code == 202, upload_resp.text
    table_id = upload_resp.json()["table_id"]

    del_resp = client.delete(f"/tables/{table_id}")
    assert del_resp.status_code == 200, del_resp.text
    assert del_resp.json()["status"] == "ARCHIVED"


def test_duplicate_upload_rejected(client: TestClient, sample_csv: bytes) -> None:
    """Same file uploaded twice → second returns REJECTED."""
    for _ in range(2):
        resp = client.post(
            "/tables",
            data={"table_name": "dup_test"},
            files={"file": ("dup.csv", io.BytesIO(sample_csv), "text/csv")},
        )
        assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "REJECTED"
