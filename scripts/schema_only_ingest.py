#!/usr/bin/env python3
"""Ingest schema-only benchmark tables without Parquet instance data."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import AsyncQdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.agents.profiling import (
    _col_sbert_input,
    _encode_with_oom_fallback,
    _table_sbert_input,
)
from adacascade.config import settings
from adacascade.db.models import Base, ColumnMetadata, TableRegistry
from adacascade.indexing.qdrant_client import AdacQdrantClient

IngestResult = Literal["created", "updated", "skipped"]


class SchemaOnlyQdrant(Protocol):
    async def upsert_table(self, **kwargs) -> None: ...

    async def upsert_columns(self, *, points: list[dict]) -> None: ...


def _table_id(prefix: str, table_name: str) -> str:
    return f"{prefix}:{table_name}"


def _column_id(table_id: str, column: dict[str, Any]) -> str:
    return str(
        column.get("column_id") or f"{table_id}:{column['ordinal']}:{column['name']}"
    )


def _content_hash(table: dict[str, Any]) -> str:
    payload = json.dumps(table, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _vector(values: Any) -> list[float]:
    return values.tolist() if hasattr(values, "tolist") else list(values)


def ingest_schema_only_table(
    db: Session,
    table: dict[str, Any],
    *,
    schema_path: Path,
    tenant_id: str,
    source_system: str,
    table_prefix: str,
    replace: bool = False,
) -> IngestResult:
    table_id = _table_id(table_prefix, str(table["table_name"]))
    existing = db.query(TableRegistry).filter_by(table_id=table_id).first()
    if existing and not replace:
        return "skipped"

    now = datetime.now(timezone.utc)
    row = existing or TableRegistry(table_id=table_id)
    if existing is None:
        db.add(row)
        result: IngestResult = "created"
    else:
        result = "updated"

    columns = list(table.get("columns", []))
    row.tenant_id = tenant_id
    row.source_system = source_system
    row.source_uri = str(schema_path)
    row.table_name = str(table["table_name"])
    row.row_count = 0
    row.col_count = len(columns)
    row.schema_hash = _content_hash(table)
    row.content_hash = _content_hash(table)
    row.uploaded_by = None
    row.uploaded_at = now if existing is None else row.uploaded_at
    row.updated_at = now
    row.status = "READY"

    db.query(ColumnMetadata).filter_by(table_id=table_id).delete()
    for column in columns:
        db.add(
            ColumnMetadata(
                column_id=_column_id(table_id, column),
                table_id=table_id,
                ordinal=int(column["ordinal"]),
                col_name=str(column["name"]),
                col_type=str(column.get("type") or "str"),
                col_description=column.get("description"),
            )
        )

    db.commit()
    return result


def ingest_schema_only_tables(
    db: Session,
    schema_path: Path,
    *,
    tenant_id: str,
    source_system: str,
    table_prefix: str,
    replace: bool = False,
) -> dict[str, int | list[str]]:
    tables = json.loads(schema_path.read_text(encoding="utf-8"))
    summary: dict[str, int | list[str]] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "table_ids": [],
    }
    for table in tables:
        table_id = _table_id(table_prefix, str(table["table_name"]))
        result = ingest_schema_only_table(
            db,
            table,
            schema_path=schema_path,
            tenant_id=tenant_id,
            source_system=source_system,
            table_prefix=table_prefix,
            replace=replace,
        )
        summary[result] = int(summary[result]) + 1
        if result != "skipped":
            table_ids = summary["table_ids"]
            assert isinstance(table_ids, list)
            table_ids.append(table_id)
    return summary


def index_schema_only_tables(
    db: Session,
    *,
    qdrant: SchemaOnlyQdrant,
    tenant_id: str,
    source_system: str,
    table_ids: list[str] | None = None,
) -> dict[str, int]:
    query = db.query(TableRegistry).filter_by(
        tenant_id=tenant_id,
        source_system=source_system,
        status="READY",
    )
    if table_ids is not None:
        query = query.filter(TableRegistry.table_id.in_(table_ids))
    tables = query.order_by(TableRegistry.table_name).all()
    batch_size: int = settings.profiling_cfg.get("sbert_batch_size", 256)
    for table in tables:
        columns = (
            db.query(ColumnMetadata)
            .filter_by(table_id=table.table_id)
            .order_by(ColumnMetadata.ordinal)
            .all()
        )
        table_vec = _vector(
            _encode_with_oom_fallback(
                [_table_sbert_input(table.table_name, columns)], batch_size
            )[0]
        )
        asyncio.run(
            qdrant.upsert_table(
                table_id=table.table_id,
                tenant_id=tenant_id,
                vector=table_vec,
                extra_payload={"table_name": table.table_name},
            )
        )
        col_vecs = _encode_with_oom_fallback(
            [_col_sbert_input(column, table.table_name) for column in columns],
            batch_size,
        )
        asyncio.run(
            qdrant.upsert_columns(
                points=[
                    {
                        "column_id": column.column_id,
                        "table_id": table.table_id,
                        "tenant_id": tenant_id,
                        "vector": _vector(col_vecs[index]),
                        "col_type": column.col_type,
                    }
                    for index, column in enumerate(columns)
                ]
            )
        )
        for column in columns:
            column.qdrant_point_id = column.column_id
    db.commit()
    return {"indexed": len(tables)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema_path", type=Path)
    parser.add_argument("--tenant-id", default="benchmark")
    parser.add_argument("--source-system", default="mimic_omop")
    parser.add_argument("--table-prefix", required=True)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--index", action="store_true")
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    with SessionFactory() as db:
        summary = ingest_schema_only_tables(
            db,
            args.schema_path,
            tenant_id=args.tenant_id,
            source_system=args.source_system,
            table_prefix=args.table_prefix,
            replace=args.replace,
        )
        if args.index:
            table_ids = summary["table_ids"]
            assert isinstance(table_ids, list)
            qdrant = AdacQdrantClient(AsyncQdrantClient(url=settings.QDRANT_URL))
            summary.update(
                index_schema_only_tables(
                    db,
                    qdrant=qdrant,
                    tenant_id=args.tenant_id,
                    source_system=args.source_system,
                    table_ids=table_ids,
                )
            )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
