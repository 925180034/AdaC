from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.db.models import Base, DatasetRegistry, TableRegistry
from scripts.backfill_datasets import backfill_datasets


def _table(table_id: str, source_system: str, tenant_id: str = "default") -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        dataset_id=None,
        source_system=source_system,
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_id,
        row_count=1,
        col_count=1,
        schema_hash=f"schema-{table_id}",
        content_hash=f"content-{table_id}",
        uploaded_by=None,
        uploaded_at=now,
        updated_at=now,
        status="READY",
    )


def test_backfill_datasets_creates_system_datasets_and_assigns_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        db.add_all(
            [
                _table("toy", "toy_lake"),
                _table("join", "retrieval|join"),
                _table("union", "retrieval|union"),
                _table("upload", "upload"),
            ]
        )
        db.commit()

        summary = backfill_datasets(db)
        second_summary = backfill_datasets(db)

        rows = {row.table_id: row.dataset_id for row in db.query(TableRegistry).all()}
        datasets = {row.dataset_id: row for row in db.query(DatasetRegistry).all()}

    assert summary == {"datasets_created": 4, "tables_updated": 4}
    assert second_summary == {"datasets_created": 0, "tables_updated": 0}
    assert rows == {
        "toy": "toy_lake",
        "join": "benchmark_join",
        "union": "benchmark_union",
        "upload": "legacy_upload",
    }
    assert set(datasets) == {"toy_lake", "benchmark_join", "benchmark_union", "legacy_upload"}
    assert all(dataset.is_system for dataset in datasets.values())
