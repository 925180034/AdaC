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
    "matcher_wikidata": "Matcher Wikidata",
    "matcher_mimic_omop": "Matcher MIMIC-OMOP",
    "legacy_upload": "Legacy Upload",
}


def _dataset_slug_for_source(source_system: str) -> str:
    if source_system == "toy_lake":
        return "toy_lake"
    if source_system == "retrieval|join":
        return "benchmark_join"
    if source_system == "retrieval|union":
        return "benchmark_union"
    if source_system == "wikidata":
        return "matcher_wikidata"
    if source_system == "mimic_omop":
        return "matcher_mimic_omop"
    return "legacy_upload"


def _dataset_id_for_source(tenant_id: str, source_system: str) -> str:
    slug = _dataset_slug_for_source(source_system)
    if tenant_id == settings.DEFAULT_TENANT_ID:
        return slug
    if slug.startswith(f"{tenant_id}_"):
        return slug
    return f"{tenant_id}_{slug}"


def backfill_datasets(db: Session) -> dict[str, int]:
    """Create system Datasets and assign existing tables without a Dataset."""
    now = datetime.now(timezone.utc)
    datasets_created = 0
    rows: list[TableRegistry] = db.query(TableRegistry).filter(TableRegistry.dataset_id.is_(None)).all()
    required_datasets = {
        (row.tenant_id, _dataset_slug_for_source(row.source_system))
        for row in rows
    }
    for tenant_id, dataset_slug in required_datasets:
        dataset_id = dataset_slug if tenant_id == settings.DEFAULT_TENANT_ID else f"{tenant_id}_{dataset_slug}"
        existing = db.query(DatasetRegistry).filter_by(dataset_id=dataset_id).first()
        if existing is None:
            db.add(
                DatasetRegistry(
                    dataset_id=dataset_id,
                    tenant_id=tenant_id,
                    dataset_name=_SYSTEM_DATASETS[dataset_slug],
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
    for row in rows:
        row.dataset_id = _dataset_id_for_source(row.tenant_id, row.source_system)
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
