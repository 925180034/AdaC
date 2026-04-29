from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.db.models import Base, ColumnMetadata, TableRegistry


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_bulk_ingest_imports_prepared_fixture_manifest(tmp_path: Path) -> None:
    from scripts.bulk_ingest import import_manifest

    table_dir = tmp_path / "fixtures" / "toy" / "table-1"
    table_dir.mkdir(parents=True)
    parquet_path = table_dir / "data.parquet"
    parquet_path.write_bytes(b"parquet placeholder")
    manifest_path = table_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "table_id": "table-1",
                "table_name": "Musicians",
                "tenant_id": "benchmark",
                "source": "toy_lake",
                "row_count": 3,
                "col_count": 2,
                "schema_hash": "schema",
                "content_hash": "content",
                "columns": [
                    {"ordinal": 0, "name": "id", "type": "int"},
                    {
                        "ordinal": 1,
                        "name": "name",
                        "type": "str",
                        "description": "artist name",
                    },
                ],
            }
        )
    )
    db = _session(tmp_path)

    result = import_manifest(db, manifest_path, default_status="INGESTED")

    table = db.query(TableRegistry).one()
    columns = db.query(ColumnMetadata).order_by(ColumnMetadata.ordinal).all()
    assert result == "created"
    assert table.table_id == "table-1"
    assert table.table_name == "Musicians"
    assert table.tenant_id == "benchmark"
    assert table.source_system == "toy_lake"
    assert table.source_uri == str(parquet_path)
    assert table.status == "INGESTED"
    assert [column.col_name for column in columns] == ["id", "name"]
    assert columns[1].col_description == "artist name"


def test_bulk_ingest_can_override_manifest_tenant(tmp_path: Path) -> None:
    from scripts.bulk_ingest import import_manifest

    table_dir = tmp_path / "fixtures" / "toy" / "table-1"
    table_dir.mkdir(parents=True)
    manifest_path = table_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "table_id": "table-1",
                "table_name": "Musicians",
                "tenant_id": "default",
                "source": "toy_lake",
                "columns": [{"ordinal": 0, "name": "id", "type": "int"}],
            }
        )
    )
    db = _session(tmp_path)

    result = import_manifest(
        db,
        manifest_path,
        default_status="INGESTED",
        tenant_id="benchmark",
    )

    table = db.query(TableRegistry).one()
    assert result == "created"
    assert table.tenant_id == "benchmark"


def test_bulk_ingest_rejects_cross_tenant_table_id_collision(tmp_path: Path) -> None:
    from scripts.bulk_ingest import import_manifest

    table_dir = tmp_path / "fixtures" / "toy" / "table-1"
    table_dir.mkdir(parents=True)
    manifest_path = table_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "table_id": "table-1",
                "table_name": "Musicians",
                "tenant_id": "default",
                "source": "toy_lake",
                "columns": [{"ordinal": 0, "name": "id", "type": "int"}],
            }
        )
    )
    db = _session(tmp_path)
    import_manifest(db, manifest_path, default_status="INGESTED")

    try:
        import_manifest(
            db,
            manifest_path,
            default_status="INGESTED",
            tenant_id="benchmark",
            replace=True,
        )
    except ValueError as exc:
        assert "already exists in tenant default" in str(exc)
    else:
        raise AssertionError("expected cross-tenant collision to fail")

    assert db.query(TableRegistry).one().tenant_id == "default"


def test_gc_removes_archived_table_records_and_files(tmp_path: Path) -> None:
    from scripts.gc import garbage_collect

    db = _session(tmp_path)
    data_dir = tmp_path / "data"
    archived_dir = data_dir / "tables" / "default" / "archived-table"
    ready_dir = data_dir / "tables" / "default" / "ready-table"
    archived_dir.mkdir(parents=True)
    ready_dir.mkdir(parents=True)
    (archived_dir / "data.parquet").write_bytes(b"archived")
    (ready_dir / "data.parquet").write_bytes(b"ready")
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            TableRegistry(
                table_id="archived-table",
                tenant_id="default",
                source_system="test",
                source_uri=str(archived_dir / "data.parquet"),
                table_name="archived",
                row_count=1,
                col_count=1,
                schema_hash="s1",
                content_hash="c1",
                uploaded_at=now,
                updated_at=now,
                status="ARCHIVED",
            ),
            TableRegistry(
                table_id="ready-table",
                tenant_id="default",
                source_system="test",
                source_uri=str(ready_dir / "data.parquet"),
                table_name="ready",
                row_count=1,
                col_count=1,
                schema_hash="s2",
                content_hash="c2",
                uploaded_at=now,
                updated_at=now,
                status="READY",
            ),
        ]
    )
    db.commit()

    summary = garbage_collect(db, data_dir=data_dir)

    remaining_ids = {row.table_id for row in db.query(TableRegistry).all()}
    assert summary == {"scanned": 1, "deleted_records": 1, "deleted_dirs": 1}
    assert remaining_ids == {"ready-table"}
    assert not archived_dir.exists()
    assert ready_dir.exists()


def test_gc_does_not_delete_source_uri_outside_data_dir(tmp_path: Path) -> None:
    from scripts.gc import garbage_collect

    db = _session(tmp_path)
    data_dir = tmp_path / "data"
    external_dir = tmp_path / "fixtures" / "external-table"
    external_dir.mkdir(parents=True)
    (external_dir / "data.parquet").write_bytes(b"external")
    now = datetime.now(timezone.utc)
    db.add(
        TableRegistry(
            table_id="external-table",
            tenant_id="default",
            source_system="fixture",
            source_uri=str(external_dir / "data.parquet"),
            table_name="external",
            row_count=1,
            col_count=1,
            schema_hash="s1",
            content_hash="c1",
            uploaded_at=now,
            updated_at=now,
            status="ARCHIVED",
        )
    )
    db.commit()

    summary = garbage_collect(db, data_dir=data_dir)

    assert summary == {"scanned": 1, "deleted_records": 1, "deleted_dirs": 0}
    assert external_dir.exists()
    assert db.query(TableRegistry).count() == 0
