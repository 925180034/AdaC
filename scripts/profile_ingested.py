#!/usr/bin/env python3
"""Profile INGESTED tables for a tenant in batches."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import AsyncQdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.agents.profiling import run_profiling
from adacascade.config import settings
from adacascade.db.models import Base, TableRegistry
from adacascade.indexing.qdrant_client import AdacQdrantClient


class ProfilingQdrant(Protocol):
    async def upsert_table(self, **kwargs) -> None: ...

    async def upsert_columns(self, *, points: list[dict]) -> None: ...


def _target_tables(
    db: Session,
    *,
    tenant_id: str,
    limit: int | None = None,
    retry_failed: bool = False,
    refresh_ready: bool = False,
    source_system: str | None = None,
) -> list[TableRegistry]:
    statuses = ["INGESTED"]
    if retry_failed:
        statuses.append("FAILED")
    if refresh_ready:
        statuses.append("READY")
    query = db.query(TableRegistry).filter(
        TableRegistry.tenant_id == tenant_id,
        TableRegistry.status.in_(statuses),
    )
    if source_system:
        query = query.filter(TableRegistry.source_system == source_system)
    query = query.filter(TableRegistry.source_uri.like("%.parquet"))
    query = query.order_by(TableRegistry.table_name)
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def profile_ingested_tables(
    db: Session,
    *,
    qdrant: ProfilingQdrant,
    tenant_id: str,
    limit: int | None = None,
    retry_failed: bool = False,
    refresh_ready: bool = False,
    source_system: str | None = None,
) -> dict[str, int]:
    tables = _target_tables(
        db,
        tenant_id=tenant_id,
        limit=limit,
        retry_failed=retry_failed,
        refresh_ready=refresh_ready,
        source_system=source_system,
    )
    summary = {"processed": len(tables), "succeeded": 0, "failed": 0}
    for table in tables:
        try:
            if table.status in {"FAILED", "READY"}:
                table.status = "INGESTED"
                db.commit()
            asyncio.run(
                run_profiling(
                    table_id=table.table_id,
                    db=db,
                    qdrant=qdrant,
                    tenant_id=tenant_id,
                )
            )
            summary["succeeded"] += 1
        except Exception:
            summary["failed"] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default=settings.DEFAULT_TENANT_ID)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--refresh-ready", action="store_true")
    parser.add_argument("--source-system")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    qdrant = AdacQdrantClient(AsyncQdrantClient(url=settings.QDRANT_URL))
    with SessionFactory() as db:
        summary = profile_ingested_tables(
            db,
            qdrant=qdrant,
            tenant_id=args.tenant_id,
            limit=args.limit,
            retry_failed=args.retry_failed,
            refresh_ready=args.refresh_ready,
            source_system=args.source_system,
        )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
