"""M3.5 task progress SSE tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adacascade.api.events import emit_task_event
from adacascade.db.models import IntegrationTask, TableRegistry
from adacascade.db.session import get_session

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token"}
TENANT_A_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-a"}
TENANT_B_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-b"}


class FakeGraph:
    """Graph test double that returns an empty successful operation state."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return successful graph output while preserving input state."""
        _ = config
        return {**state, "ranking": [], "final_mappings": []}


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a TestClient with external startup dependencies mocked."""
    mock_qdrant = MagicMock()
    mock_qdrant.delete_table = AsyncMock()
    raw_qdrant_mock = AsyncMock()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch("adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)),
    ):
        from adacascade.api.app import app

        with TestClient(app, raise_server_exceptions=False) as c:
            _seed_sse_task()
            yield c


def _seed_sse_task() -> None:
    now = datetime.now(timezone.utc)
    with get_session() as db:
        if db.query(IntegrationTask).filter_by(task_id="sse-task-a").first() is None:
            db.add(
                IntegrationTask(
                    task_id="sse-task-a",
                    tenant_id="tenant-a",
                    task_type="DISCOVER_ONLY",
                    query_table_id=None,
                    target_table_id=None,
                    plan_config="{}",
                    status="RUNNING",
                    submitted_at=now,
                    finished_at=None,
                    error_message=None,
                    artifacts_dir=None,
                )
            )
        for table_id, tenant_id in [
            ("sse-query", "tenant-a"),
            ("sse-query-running", "tenant-a"),
            ("tenant-b-only-table", "tenant-b"),
        ]:
            if db.query(TableRegistry).filter_by(table_id=table_id).first() is None:
                db.add(
                    TableRegistry(
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
                )


def _poll_task(client: TestClient, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}", headers=TENANT_A_HEADERS)
        assert response.status_code == 200, response.text
        last_body = response.json()
        if last_body["status"] != "RUNNING":
            return last_body
        time.sleep(0.01)
    assert last_body is not None
    return last_body


def test_wrong_tenant_task_events_returns_404(client: TestClient) -> None:
    response = client.get("/tasks/sse-task-a/events", headers=TENANT_B_HEADERS)
    assert response.status_code == 404


def test_pre_emitted_task_events_stream_from_history(client: TestClient) -> None:
    asyncio.run(
        emit_task_event("sse-task-a", {"type": "agent_started", "agent": "Retrieval"})
    )
    asyncio.run(
        emit_task_event("sse-task-a", {"type": "task_completed", "status": "SUCCESS"})
    )

    with client.stream("GET", "/tasks/sse-task-a/events", headers=TENANT_A_HEADERS) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert "event: agent_started" in body
    assert '"agent":"Retrieval"' in body
    assert "event: task_completed" in body


def test_discover_rejects_cross_tenant_query_table(client: TestClient) -> None:
    response = client.post(
        "/discover",
        json={"query_table_id": "tenant-b-only-table"},
        headers=TENANT_A_HEADERS,
    )

    assert response.status_code == 404


def test_discover_route_emits_lifecycle_event_history(client: TestClient) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakeGraph()
    try:
        create_response = client.post(
            "/discover",
            json={"query_table_id": "sse-query"},
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    create_body = create_response.json()
    assert create_body["status"] == "RUNNING"
    task_id = str(create_body["task_id"])

    task = _poll_task(client, task_id)
    assert task["status"] == "SUCCESS"

    with client.stream("GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert "event: task_created" in body
    assert "event: agent_started" in body
    assert "event: agent_completed" in body
    assert "event: task_completed" in body


def test_discover_route_returns_running_before_final_status(client: TestClient) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakeGraph()
    try:
        create_response = client.post(
            "/discover",
            json={"query_table_id": "sse-query-running"},
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    create_body = create_response.json()
    assert create_body["status"] == "RUNNING"
    assert create_body["state"]["status"] == "RUNNING"
    assert create_body["task_id"]

    task = _poll_task(client, str(create_body["task_id"]))
    assert task["status"] == "SUCCESS"
