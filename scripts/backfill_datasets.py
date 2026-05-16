#!/usr/bin/env python3
"""Backfill Dataset registry rows and table Dataset assignments."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from adacascade.config import settings
from adacascade.db.models import DatasetRegistry, TableRegistry
from adacascade.db.session import get_session, init_db

_SYSTEM_DATASETS: dict[str, str] = {
    "toy_lake": "Toy Lake",
    "benchmark_join": "Benchmark JOIN",
    "benchmark_union": "Benchmark UNION",
    "legacy_upload": "Legacy Upload",
}


def _dataset_id_for_source(source_system: str) -> str:
    if source_system == "toy_lake":
        return "toy_lake"
    if source_system == "retrieval|join":
        return "benchmark_join"
    if source_system == "retrieval|union":
        return "benchmark_union"
    return "legacy_upload"


def backfill_datasets(db: Session) -> dict[str, int]:
    """Create system Datasets and assign existing tables without a Dataset."""
    now = datetime.now(timezone.utc)
    datasets_created = 0
    for dataset_id, dataset_name in _SYSTEM_DATASETS.items():
        existing = db.query(DatasetRegistry).filter_by(dataset_id=dataset_id).first()
        if existing is None:
            db.add(
                DatasetRegistry(
                    dataset_id=dataset_id,
                    tenant_id=settings.DEFAULT_TENANT_ID,
                    dataset_name=dataset_name,
                    description=None,
                    created_by="system",
                    created_at=now,
                    updated_at=now,
                    status="ACTIVE",
                    is_system=True,
                )
            )
            datasets_created += 1
    db.flush()

    tables_updated = 0
    rows: list[TableRegistry] = db.query(TableRegistry).filter(TableRegistry.dataset_id.is_(None)).all()
    for row in rows:
        row.dataset_id = _dataset_id_for_source(row.source_system)
        row.updated_at = now
        tables_updated += 1
    db.commit()
    return {"datasets_created": datasets_created, "tables_updated": tables_updated}


def main() -> None:
    """Run Dataset backfill using configured database settings."""
    init_db(settings.DATABASE_URL)
    with get_session() as db:
        summary = backfill_datasets(db)
    print(summary)


if __name__ == "__main__":
    main()
