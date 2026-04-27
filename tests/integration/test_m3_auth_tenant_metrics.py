"""M3 auth, tenant isolation, and metrics tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adacascade.db.models import IntegrationTask, TableRegistry
from adacascade.db.session import get_session

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token"}
TENANT_A_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-a"}
TENANT_B_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-b"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    mock_qdrant = MagicMock()
    mock_qdrant.delete_table = AsyncMock()
    raw_qdrant_mock = AsyncMock()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch(
            "adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)
        ),
    ):
        from adacascade.api.app import app

        with TestClient(app, raise_server_exceptions=False) as c:
            _seed_tenant_rows()
            yield c


def _table(table_id: str, tenant_id: str) -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        source_system="test",
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_id,
        row_count=1,
        col_count=1,
        schema_hash=table_id,
        content_hash=table_id,
        uploaded_by=None,
        uploaded_at=now,
        updated_at=now,
        status="READY",
    )


def _seed_tenant_rows() -> None:
    now = datetime.now(timezone.utc)
    with get_session() as db:
        for table_id, tenant_id in [
            ("tenant_a_table", "tenant-a"),
            ("tenant_b_table", "tenant-b"),
        ]:
            if db.query(TableRegistry).filter_by(table_id=table_id).first() is None:
                db.add(_table(table_id, tenant_id))
        if db.query(IntegrationTask).filter_by(task_id="tenant-a-task").first() is None:
            db.add(
                IntegrationTask(
                    task_id="tenant-a-task",
                    tenant_id="tenant-a",
                    task_type="DISCOVER_ONLY",
                    query_table_id="tenant_a_table",
                    target_table_id=None,
                    plan_config="{}",
                    status="SUCCESS",
                    submitted_at=now,
                    finished_at=now,
                    error_message=None,
                    artifacts_dir=None,
                )
            )


def test_public_healthz_and_metrics(client: TestClient) -> None:
    health = client.get("/healthz")
    assert health.status_code == 200
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "http_requests" in metrics.text or "python_info" in metrics.text


def test_protected_route_requires_bearer_token(client: TestClient) -> None:
    missing = client.get("/tables")
    assert missing.status_code == 401
    bad = client.get("/tables", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    ok = client.get("/tables", headers=AUTH_HEADERS)
    assert ok.status_code == 200


def test_tenant_header_scopes_tables(client: TestClient) -> None:
    tenant_a = client.get("/tables", headers=TENANT_A_HEADERS).json()["items"]
    tenant_b = client.get("/tables", headers=TENANT_B_HEADERS).json()["items"]
    assert {item["table_id"] for item in tenant_a} >= {"tenant_a_table"}
    assert "tenant_b_table" not in {item["table_id"] for item in tenant_a}
    assert {item["table_id"] for item in tenant_b} >= {"tenant_b_table"}


def test_tenant_header_scopes_tasks(client: TestClient) -> None:
    visible = client.get("/tasks/tenant-a-task", headers=TENANT_A_HEADERS)
    hidden = client.get("/tasks/tenant-a-task", headers=TENANT_B_HEADERS)
    assert visible.status_code == 200
    assert hidden.status_code == 404
