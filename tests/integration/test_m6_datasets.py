from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
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


def _write_preview_table(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "farm_id": 1,
                "crop_name": "wheat",
                "soil_ph": 6.5,
                "measurements": [1, 2],
                "observed_at": pd.NaT,
            },
            {
                "farm_id": 2,
                "crop_name": None,
                "soil_ph": 7.1,
                "measurements": None,
                "observed_at": pd.Timestamp("2026-05-25T09:30:00"),
            },
        ]
    ).to_parquet(path, index=False)


def _set_table_source_uri(table_id: str, source_uri: Path) -> None:
    with get_session() as db:
        table = db.query(TableRegistry).filter_by(table_id=table_id).one()
        table.source_uri = str(source_uri)
        db.commit()


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


def test_dataset_listing_prioritizes_ready_datasets() -> None:
    with next(client_fixture()) as client:
        listed = client.get("/datasets", headers=TENANT_A_HEADERS)
        assert listed.status_code == 200
        dataset_ids = [item["dataset_id"] for item in listed.json()["items"]]
        assert dataset_ids.index("dataset-a") < dataset_ids.index("system-a")


def test_tables_can_be_filtered_by_dataset() -> None:
    with next(client_fixture()) as client:
        scoped = client.get("/tables?dataset_id=dataset-a", headers=TENANT_A_HEADERS)
        assert scoped.status_code == 200
        table_ids = {item["table_id"] for item in scoped.json()["items"]}
        assert table_ids == {"table-a", "table-a-2"}
        assert all(item["dataset_id"] == "dataset-a" for item in scoped.json()["items"])


def test_table_preview_returns_metadata_columns_and_sample_rows(tmp_path: Path) -> None:
    preview_path = tmp_path / "table-a.parquet"
    _write_preview_table(preview_path)

    with next(client_fixture()) as client:
        _set_table_source_uri("table-a", preview_path)
        response = client.get(
            "/tables/table-a/preview?dataset_id=dataset-a&limit=1",
            headers=TENANT_A_HEADERS,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["table"]["table_id"] == "table-a"
    assert body["table"]["dataset_id"] == "dataset-a"
    assert body["columns"] == ["farm_id", "crop_name", "soil_ph", "measurements", "observed_at"]
    assert body["sample_rows"] == [
        {
            "farm_id": 1,
            "crop_name": "wheat",
            "soil_ph": 6.5,
            "measurements": [1, 2],
            "observed_at": None,
        }
    ]
    assert body["sample_limit"] == 1


def test_table_preview_rejects_dataset_mismatch(tmp_path: Path) -> None:
    preview_path = tmp_path / "table-a.parquet"
    _write_preview_table(preview_path)

    with next(client_fixture()) as client:
        _set_table_source_uri("table-a", preview_path)
        response = client.get(
            "/tables/table-a/preview?dataset_id=system-a",
            headers=TENANT_A_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Table not found"


def test_table_preview_rejects_other_tenant_table(tmp_path: Path) -> None:
    preview_path = tmp_path / "table-b.parquet"
    _write_preview_table(preview_path)

    with next(client_fixture()) as client:
        _set_table_source_uri("table-b", preview_path)
        response = client.get("/tables/table-b/preview", headers=TENANT_A_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "Table not found"


def test_table_preview_reports_missing_data_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-table-a.parquet"

    with next(client_fixture()) as client:
        _set_table_source_uri("table-a", missing_path)
        response = client.get("/tables/table-a/preview", headers=TENANT_A_HEADERS)

    assert response.status_code == 404
    assert response.json()["detail"] == "Table data file not found"


def test_table_preview_resolves_relative_source_uri_from_data_dir_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    preview_path = runtime_root / "data" / "tables" / "tenant-a" / "table-a" / "data.parquet"
    _write_preview_table(preview_path)

    monkeypatch.setattr("adacascade.api.routes.tables.settings.DATA_DIR", str(runtime_root / "data"))

    with next(client_fixture()) as client:
        _set_table_source_uri("table-a", Path("data/tables/tenant-a/table-a/data.parquet"))
        response = client.get(
            "/tables/table-a/preview?dataset_id=dataset-a&limit=1",
            headers=TENANT_A_HEADERS,
        )

    assert response.status_code == 200, response.text
    assert response.json()["sample_rows"][0]["crop_name"] == "wheat"


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


def test_dataset_upload_rejects_too_many_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.api.routes.datasets.settings.MAX_UPLOAD_FILE_COUNT", 1)

    with next(client_fixture()) as client:
        response = client.post(
            "/datasets/dataset-a/tables",
            files=[
                ("files", ("people.csv", b"id,name\n1,Ada\n", "text/csv")),
                ("files", ("places.csv", b"id,place\n1,London\n", "text/csv")),
            ],
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 413
        assert response.json()["detail"] == "Too many files; maximum is 1"


def test_dataset_upload_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.api.routes.datasets.settings.MAX_UPLOAD_FILE_BYTES", 4)

    with next(client_fixture()) as client:
        response = client.post(
            "/datasets/dataset-a/tables",
            files={"files": ("people.csv", b"id,name\n1,Ada\n", "text/csv")},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 413
        assert response.json()["detail"] == "people.csv exceeds maximum upload size"


def test_legacy_table_upload_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.api.routes.tables.settings.MAX_UPLOAD_FILE_BYTES", 4)

    with next(client_fixture()) as client:
        response = client.post(
            "/tables",
            files={"file": ("people.csv", b"id,name\n1,Ada\n", "text/csv")},
            data={"table_name": "people"},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 413
        assert response.json()["detail"] == "upload exceeds maximum file size"


def test_dataset_upload_commits_before_background_profiling(monkeypatch: pytest.MonkeyPatch) -> None:
    profiled_statuses: list[str] = []

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):  # type: ignore[no-untyped-def]
        profiled_statuses.append(db.query(TableRegistry).filter_by(table_id=table_id).one().status)
        db.query(TableRegistry).filter_by(table_id=table_id).update({"status": "READY"})
        db.commit()

    monkeypatch.setattr("adacascade.agents.profiling.run_profiling", fake_run_profiling)

    with next(client_fixture()) as client:
        response = client.post(
            "/datasets/dataset-a/tables",
            files={"files": ("people_unique_for_background.csv", b"id,name\n42,Ada\n", "text/csv")},
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 202, response.text
        accepted = response.json()["accepted"]
        assert len(accepted) == 1

    assert profiled_statuses == ["INGESTED"]


def test_dataset_upload_profiles_later_tables_when_one_profile_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted: list[str] = []

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):  # type: ignore[no-untyped-def]
        attempted.append(table_id)
        table = db.query(TableRegistry).filter_by(table_id=table_id).one()
        if len(attempted) == 1:
            table.status = "FAILED"
            db.commit()
            raise RuntimeError("boom")
        table.status = "READY"
        db.commit()

    monkeypatch.setattr("adacascade.agents.profiling.run_profiling", fake_run_profiling)

    with next(client_fixture()) as client:
        response = client.post(
            "/datasets/dataset-a/tables",
            files=[
                ("files", ("first_failure_case.csv", b"id,name\n101,Ada\n", "text/csv")),
                ("files", ("second_success_case.csv", b"id,name\n202,Grace\n", "text/csv")),
            ],
            headers=TENANT_A_HEADERS,
        )
        assert response.status_code == 202, response.text
        accepted = response.json()["accepted"]
        assert len(accepted) == 2
        accepted_ids = [item["table_id"] for item in accepted]

    with get_session() as db:
        statuses = {
            table_id: db.query(TableRegistry).filter_by(table_id=table_id).one().status
            for table_id in accepted_ids
        }

    assert attempted == accepted_ids
    assert statuses[accepted_ids[0]] == "FAILED"
    assert statuses[accepted_ids[1]] == "READY"
