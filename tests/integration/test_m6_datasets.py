from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from adacascade.db.models import ColumnMetadata, DatasetRegistry, TableRegistry
from adacascade.db.session import get_session

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token"}
TENANT_A_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-a"}
TENANT_B_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-b"}


class FakeGraph:
    async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, object]:
        return {**state, "ranking": [], "final_mappings": []}


def _dataset(dataset_id: str, tenant_id: str, name: str, *, is_system: bool = False) -> DatasetRegistry:
    now = datetime.now(timezone.utc)
    return DatasetRegistry(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        dataset_name=name,
        description=None,
        created_by="test",
        created_at=now,
        updated_at=now,
        status="ACTIVE",
        is_system=is_system,
    )


def _table(table_id: str, tenant_id: str, dataset_id: str, *, status: str = "READY") -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        source_system="test",
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_id,
        row_count=1,
        col_count=1,
        schema_hash=f"schema-{table_id}",
        content_hash=f"content-{table_id}",
        uploaded_by=None,
        uploaded_at=now,
        updated_at=now,
        status=status,
    )


def _seed() -> None:
    with get_session() as db:
        for row in [
            _dataset("dataset-a", "tenant-a", "Dataset A"),
            _dataset("dataset-b", "tenant-b", "Dataset B"),
            _dataset("system-a", "tenant-a", "System A", is_system=True),
        ]:
            if db.query(DatasetRegistry).filter_by(dataset_id=row.dataset_id).first() is None:
                db.add(row)
        for row in [
            _table("table-a", "tenant-a", "dataset-a"),
            _table("table-a-2", "tenant-a", "dataset-a", status="FAILED"),
            _table("table-b", "tenant-b", "dataset-b"),
            _table("system-table", "tenant-a", "system-a"),
        ]:
            if db.query(TableRegistry).filter_by(table_id=row.table_id).first() is None:
                db.add(row)
                db.add(
                    ColumnMetadata(
                        column_id=f"{row.table_id}-col",
                        table_id=row.table_id,
                        ordinal=0,
                        col_name="name",
                        col_type="str",
                        col_description=None,
                        null_ratio=0.0,
                        distinct_ratio=1.0,
                        stat_summary=None,
                        qdrant_point_id=None,
                    )
                )


def client_fixture() -> Generator[TestClient, None, None]:
    mock_qdrant = MagicMock()
    mock_qdrant.delete_table = AsyncMock()
    raw_qdrant_mock = AsyncMock()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch("adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)),
    ):
        from adacascade.api.app import app

        with TestClient(app, raise_server_exceptions=False) as client:
            app.state.graph = FakeGraph()
            _seed()
            yield client


def test_create_and_list_datasets() -> None:
    with next(client_fixture()) as client:
        create = client.post(
            "/datasets",
            json={"dataset_name": "  New Lake  ", "description": "demo"},
            headers=TENANT_A_HEADERS,
        )
        assert create.status_code == 201, create.text
        created = create.json()
        assert created["dataset_name"] == "New Lake"
        assert created["description"] == "demo"
        assert created["is_system"] is False

        duplicate = client.post("/datasets", json={"dataset_name": "New Lake"}, headers=TENANT_A_HEADERS)
        assert duplicate.status_code == 409

        same_name_other_tenant = client.post("/datasets", json={"dataset_name": "New Lake"}, headers=TENANT_B_HEADERS)
        assert same_name_other_tenant.status_code == 201, same_name_other_tenant.text

        listed = client.get("/datasets", headers=TENANT_A_HEADERS)
        assert listed.status_code == 200
        items = {item["dataset_id"]: item for item in listed.json()["items"]}
        assert "dataset-a" in items
        assert "dataset-b" not in items
        assert items["dataset-a"]["table_count"] == 2
        assert items["dataset-a"]["ready_count"] == 1
        assert items["dataset-a"]["failed_count"] == 1


def test_tables_can_be_filtered_by_dataset() -> None:
    with next(client_fixture()) as client:
        scoped = client.get("/tables?dataset_id=dataset-a", headers=TENANT_A_HEADERS)
        assert scoped.status_code == 200
        table_ids = {item["table_id"] for item in scoped.json()["items"]}
        assert table_ids == {"table-a", "table-a-2"}
        assert all(item["dataset_id"] == "dataset-a" for item in scoped.json()["items"])


def test_task_initial_state_and_plan_include_dataset_id() -> None:
    with next(client_fixture()) as client:
        response = client.post(
            "/discover",
            json={"query_table_id": "table-a", "dataset_id": "dataset-a"},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"]["dataset_id"] == "dataset-a"
        assert body["state"]["plan"]["dataset_id"] == "dataset-a"


def test_task_rejects_table_outside_dataset() -> None:
    with next(client_fixture()) as client:
        response = client.post(
            "/discover",
            json={"query_table_id": "table-a", "dataset_id": "system-a"},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 404


def test_system_dataset_rejects_uploads() -> None:
    with next(client_fixture()) as client:
        response = client.post(
            "/datasets/system-a/tables",
            files={"files": ("people.csv", b"id,name\n1,Ada\n", "text/csv")},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 403
