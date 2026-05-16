from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.db.models import Base, DatasetRegistry, TableRegistry


def test_dataset_registry_has_product_fields_and_table_relationship() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)

    with session_factory() as db:
        dataset = DatasetRegistry(
            dataset_id="dataset-a",
            tenant_id="tenant-a",
            dataset_name="Dataset A",
            description="demo dataset",
            created_by="tester",
            created_at=now,
            updated_at=now,
            status="ACTIVE",
            is_system=False,
        )
        table = TableRegistry(
            table_id="table-a",
            tenant_id="tenant-a",
            dataset_id="dataset-a",
            source_system="upload",
            source_uri="/tmp/table-a.parquet",
            table_name="table-a",
            row_count=1,
            col_count=1,
            schema_hash="schema",
            content_hash="content",
            uploaded_by="tester",
            uploaded_at=now,
            updated_at=now,
            status="INGESTED",
        )
        db.add_all([dataset, table])
        db.commit()

        stored = db.query(DatasetRegistry).filter_by(dataset_id="dataset-a").one()
        assert stored.dataset_name == "Dataset A"
        assert stored.description == "demo dataset"
        assert stored.created_by == "tester"
        assert stored.status == "ACTIVE"
        assert stored.is_system is False
        assert [row.table_id for row in stored.tables] == ["table-a"]
