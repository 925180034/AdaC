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


class FakePopulatedGraph:
    """Graph test double that returns ranking and mapping outputs."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return populated graph output while preserving input state."""
        _ = config
        return {
            **state,
            "ranking": [
                {
                    "table_id": "candidate-table",
                    "score": 0.91,
                    "layer_scores": {"s1": 0.8, "s2": 0.88, "s3": 0.94},
                }
            ],
            "final_mappings": [
                {
                    "source_col_id": "source.name",
                    "target_col_id": "target.full_name",
                    "scenario": "SMD",
                    "confidence": 0.87,
                    "reasoning": "same semantic column",
                }
            ],
        }


class FakeEmptyColumnGraph:
    """Graph test double that only emits matcher start for unusable columns."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return empty mapping output after emitting a matcher filtering start."""
        _ = config
        await emit_task_event(
            str(state["task_id"]),
            {
                "type": "agent_started",
                "agent": "Matcher",
                "layer": "filtering",
                "status": "RUNNING",
                "input_size": 0,
            },
        )
        return {**state, "ranking": [], "final_mappings": []}


class FakeDegradedRetrievalGraph:
    """Graph test double that emits a degraded retrieval terminal event."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return empty output after marking retrieval L2 degraded."""
        _ = config
        await emit_task_event(
            str(state["task_id"]),
            {
                "type": "agent_degraded",
                "agent": "Retrieval",
                "layer": "L2",
                "status": "DEGRADED",
                "output_size": 0,
                "reason": "vector search fallback",
            },
        )
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
        patch(
            "adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)
        ),
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
            ("sse-query-populated", "tenant-a"),
            ("sse-source", "tenant-a"),
            ("sse-target", "tenant-a"),
            ("sse-empty-source", "tenant-a"),
            ("sse-empty-target", "tenant-a"),
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


def test_cancel_running_task_marks_failed_and_emits_terminal_event(
    client: TestClient,
) -> None:
    response = client.post("/tasks/sse-task-a/cancel", headers=TENANT_A_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error_message"] == "Task cancelled by user"
    assert body["finished_at"] is not None

    with get_session() as db:
        task = db.query(IntegrationTask).filter_by(task_id="sse-task-a").one()
        assert task.status == "FAILED"
        assert task.error_message == "Task cancelled by user"

    with client.stream(
        "GET", "/tasks/sse-task-a/events", headers=TENANT_A_HEADERS
    ) as stream_response:
        assert stream_response.status_code == 200
        event_body = stream_response.read().decode()

    assert "event: task_completed" in event_body
    assert '"status":"FAILED"' in event_body
    assert "Task cancelled by user" in event_body


def test_cancel_cross_tenant_task_returns_404(client: TestClient) -> None:
    response = client.post("/tasks/sse-task-a/cancel", headers=TENANT_B_HEADERS)

    assert response.status_code == 404


def test_pre_emitted_task_events_stream_from_history(client: TestClient) -> None:
    asyncio.run(
        emit_task_event("sse-task-a", {"type": "agent_started", "agent": "Retrieval"})
    )
    asyncio.run(
        emit_task_event("sse-task-a", {"type": "task_completed", "status": "SUCCESS"})
    )

    with client.stream(
        "GET", "/tasks/sse-task-a/events", headers=TENANT_A_HEADERS
    ) as response:
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

    with client.stream(
        "GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert "event: task_created" in body
    assert '"agent":"Planner","status":"RUNNING"' in body
    assert '"agent":"Planner","status":"SUCCESS"' in body
    assert '"agent":"Profiling","status":"RUNNING"' in body
    assert '"agent":"Profiling","status":"SUCCESS"' in body
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


def test_integrate_route_emits_retrieval_and_matcher_stage_events(
    client: TestClient,
) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakePopulatedGraph()
    try:
        create_response = client.post(
            "/integrate",
            json={"query_table_id": "sse-query-populated"},
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    task_id = str(create_response.json()["task_id"])
    task = _poll_task(client, task_id)
    assert task["status"] == "SUCCESS"

    with client.stream(
        "GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    for layer in ["L1", "L2", "L3"]:
        assert f'"agent":"Retrieval","layer":"{layer}"' in body
    for layer in ["filtering", "LLM", "decision"]:
        assert f'"agent":"Matcher","layer":"{layer}"' in body


def test_discover_route_preserves_degraded_retrieval_stage(client: TestClient) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakeDegradedRetrievalGraph()
    try:
        create_response = client.post(
            "/discover",
            json={"query_table_id": "sse-query"},
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    task_id = str(create_response.json()["task_id"])
    task = _poll_task(client, task_id)
    assert task["status"] == "SUCCESS"

    with client.stream(
        "GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert '"agent":"Retrieval","layer":"L2","status":"DEGRADED"' in body
    assert '"agent":"Retrieval","layer":"L2","status":"SUCCESS"' not in body


def test_match_route_emits_matcher_stage_events(client: TestClient) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakePopulatedGraph()
    try:
        create_response = client.post(
            "/match",
            json={"source_table_id": "sse-source", "target_table_id": "sse-target"},
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    task_id = str(create_response.json()["task_id"])
    task = _poll_task(client, task_id)
    assert task["status"] == "SUCCESS"

    with client.stream(
        "GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    for layer in ["filtering", "LLM", "decision"]:
        assert f'"agent":"Matcher","layer":"{layer}"' in body


def test_match_route_backfills_completion_for_started_empty_stage(
    client: TestClient,
) -> None:
    app_state = cast(Any, client.app).state
    previous_graph = app_state.graph
    app_state.graph = FakeEmptyColumnGraph()
    try:
        create_response = client.post(
            "/match",
            json={
                "source_table_id": "sse-empty-source",
                "target_table_id": "sse-empty-target",
            },
            headers=TENANT_A_HEADERS,
        )
    finally:
        app_state.graph = previous_graph

    assert create_response.status_code == 200
    task_id = str(create_response.json()["task_id"])
    task = _poll_task(client, task_id)
    assert task["status"] == "SUCCESS"

    with client.stream(
        "GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS
    ) as response:
        assert response.status_code == 200
        body = response.read().decode()

    assert '"agent":"Matcher","layer":"filtering","status":"RUNNING"' in body
    assert '"agent":"Matcher","layer":"filtering","status":"SUCCESS"' in body
