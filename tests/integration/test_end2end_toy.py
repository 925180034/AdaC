"""Toy endpoint coverage for M2 operation routes."""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from datetime import datetime, timezone
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
    ):
        from adacascade.api.app import app

        class FakeGraph:
            async def ainvoke(
                self, state: dict[str, object], config: dict[str, object]
            ) -> dict[str, object]:
                return {
                    **state,
                    "ranking": [
                        {
                            "table_id": "toy_target",
                            "score": 0.91,
                            "layer_scores": {"s1": 0.8, "s2": 0.9, "s3": 0.95},
                        }
                    ],
                    "final_mappings": [
                        {
                            "source_col_id": "src_name",
                            "target_col_id": "tgt_name",
                            "scenario": "SMD",
                            "confidence": 0.9,
                            "reasoning": "same column",
                        }
                    ],
                }

        with TestClient(app, raise_server_exceptions=False) as c:
            app.state.graph = FakeGraph()
            _seed_ready_tables()
            yield c


def _table(table_id: str, name: str) -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=settings.DEFAULT_TENANT_ID,
        source_system="test",
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=name,
        row_count=2,
        col_count=1,
        schema_hash=table_id,
        content_hash=table_id,
        uploaded_by=None,
        uploaded_at=now,
        updated_at=now,
        status="READY",
    )


def _seed_ready_tables() -> None:
    with get_session() as db:
        for table_id, name, col_id in [
            ("toy_source", "toy source", "src_name"),
            ("toy_target", "toy target", "tgt_name"),
        ]:
            if db.query(TableRegistry).filter_by(table_id=table_id).first() is None:
                db.add(_table(table_id, name))
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
                        stat_summary=json.dumps(
                            {"cat_top_k": [["alice", 0.5], ["bob", 0.5]]}
                        ),
                        qdrant_point_id=col_id,
                    )
                )


def _poll_task(client: TestClient, task_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 2.0
    last_body: dict[str, object] | None = None
    while time.monotonic() < deadline:
        task_resp = client.get(f"/tasks/{task_id}", headers=AUTH_HEADERS)
        assert task_resp.status_code == 200, task_resp.text
        last_body = task_resp.json()
        if last_body["status"] != "RUNNING":
            return last_body
        time.sleep(0.01)
    assert last_body is not None
    return last_body


def test_integrate_and_task_status(client: TestClient) -> None:
    resp = client.post(
        "/integrate", json={"query_table_id": "toy_source"}, headers=AUTH_HEADERS
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "RUNNING"
    assert body["state"]["status"] == "RUNNING"
    assert body["task_id"]

    task_body = _poll_task(client, str(body["task_id"]))
    assert task_body["status"] == "SUCCESS"
    ranking = task_body["ranking"]
    mappings = task_body["mappings"]
    assert isinstance(ranking, list)
    assert isinstance(mappings, list)
    assert ranking[0]["candidate_table"] == "toy_target"
    assert mappings[0]["src_column_id"] == "src_name"
