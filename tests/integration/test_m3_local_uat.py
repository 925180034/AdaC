"""M3 local UAT coverage for integrate/discover/match routes."""

from __future__ import annotations

import time
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, TableRegistry
from adacascade.db.session import get_session

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token"}


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
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

        class FakeGraph:
            async def ainvoke(
                self, state: dict[str, object], config: dict[str, object]
            ) -> dict[str, object]:
                task_type = state["task_type"]
                ranking = (
                    []
                    if task_type == "MATCH_ONLY"
                    else [
                        {
                            "table_id": "uat_target",
                            "score": 0.9,
                            "layer_scores": {"s1": 0.8, "s2": 0.9, "s3": 0.95},
                        }
                    ]
                )
                mappings = (
                    []
                    if task_type == "DISCOVER_ONLY"
                    else [
                        {
                            "source_col_id": "uat_src_col",
                            "target_col_id": "uat_tgt_col",
                            "scenario": "SMD",
                            "confidence": 0.88,
                            "reasoning": "local uat",
                        }
                    ]
                )
                return {**state, "ranking": ranking, "final_mappings": mappings}

        with TestClient(app, raise_server_exceptions=False) as c:
            app.state.graph = FakeGraph()
            _seed_uat_tables()
            yield c


def _seed_uat_tables() -> None:
    now = datetime.now(timezone.utc)
    with get_session() as db:
        for table_id, col_id in [
            ("uat_source", "uat_src_col"),
            ("uat_target", "uat_tgt_col"),
        ]:
            if db.query(TableRegistry).filter_by(table_id=table_id).first() is None:
                db.add(
                    TableRegistry(
                        table_id=table_id,
                        tenant_id=settings.DEFAULT_TENANT_ID,
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
                db.add(
                    ColumnMetadata(
                        column_id=col_id,
                        table_id=table_id,
                        ordinal=0,
                        col_name="name",
                        col_type="str",
                        col_description="name",
                        null_ratio=0.0,
                        distinct_ratio=1.0,
                        stat_summary=None,
                        qdrant_point_id=col_id,
                    )
                )


def _poll_task(client: TestClient, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 2.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        task_resp = client.get(f"/tasks/{task_id}", headers=AUTH_HEADERS)
        assert task_resp.status_code == 200, task_resp.text
        last_body = task_resp.json()
        if last_body["status"] != "RUNNING":
            return last_body
        time.sleep(0.01)
    assert last_body is not None
    return last_body


@pytest.mark.parametrize(
    ("path", "payload", "expect_ranking", "expect_mapping"),
    [
        ("/integrate", {"query_table_id": "uat_source"}, True, True),
        ("/discover", {"query_table_id": "uat_source"}, True, False),
        (
            "/match",
            {"source_table_id": "uat_source", "target_table_id": "uat_target"},
            False,
            True,
        ),
    ],
)
def test_local_uat_routes(
    client: TestClient,
    path: str,
    payload: dict[str, str],
    expect_ranking: bool,
    expect_mapping: bool,
) -> None:
    resp = client.post(path, json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "RUNNING"
    assert body["state"]["status"] == "RUNNING"
    assert body["task_id"]

    task = _poll_task(client, str(body["task_id"]))
    assert task["status"] == "SUCCESS"
    assert bool(task["ranking"]) is expect_ranking
    assert bool(task["mappings"]) is expect_mapping
