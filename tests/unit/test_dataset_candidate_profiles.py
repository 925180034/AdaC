from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.agents.profiling import load_candidate_profiles
from adacascade.db.models import Base, ColumnMetadata, DatasetRegistry, TableRegistry


def _dataset(dataset_id: str, tenant_id: str) -> DatasetRegistry:
    now = datetime.now(timezone.utc)
    return DatasetRegistry(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        dataset_name=dataset_id,
        description=None,
        created_by="test",
        created_at=now,
        updated_at=now,
        status="ACTIVE",
        is_system=False,
    )


def _table(table_id: str, tenant_id: str, dataset_id: str) -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        source_system="upload",
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_id,
        row_count=1,
        col_count=1,
        schema_hash=f"schema-{table_id}",
        content_hash=f"content-{table_id}",
        uploaded_by="test",
        uploaded_at=now,
        updated_at=now,
        status="READY",
    )


def _column(table_id: str) -> ColumnMetadata:
    return ColumnMetadata(
        column_id=f"{table_id}-col",
        table_id=table_id,
        ordinal=0,
        col_name="name",
        col_type="str",
        col_description=None,
        null_ratio=0.0,
        distinct_ratio=1.0,
        stat_summary=None,
        qdrant_point_id=None,
    )


def _seed(db: Session) -> None:
    db.add_all([
        _dataset("dataset-a", "tenant-a"),
        _dataset("dataset-b", "tenant-a"),
    ])
    for table in [
        _table("query", "tenant-a", "dataset-a"),
        _table("candidate-a", "tenant-a", "dataset-a"),
        _table("candidate-b", "tenant-a", "dataset-b"),
    ]:
        db.add(table)
        db.add(_column(table.table_id))
    db.commit()


def test_load_candidate_profiles_filters_by_dataset_id() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        _seed(db)

        profiles = load_candidate_profiles(
            "query",
            "tenant-a",
            db,
            dataset_id="dataset-a",
        )

    assert set(profiles) == {"candidate-a"}
