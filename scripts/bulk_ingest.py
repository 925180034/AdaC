#!/usr/bin/env python3
"""Bulk-import prepared fixture manifests into metadata DB."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.config import settings
from adacascade.db.models import Base, ColumnMetadata, TableRegistry

ImportResult = Literal["created", "updated", "skipped"]


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _column_id(table_id: str, column: dict[str, Any]) -> str:
    return str(
        column.get("column_id") or f"{table_id}:{column['ordinal']}:{column['name']}"
    )


def import_manifest(
    db: Session,
    manifest_path: Path,
    *,
    default_status: str = "INGESTED",
    replace: bool = False,
    tenant_id: str | None = None,
) -> ImportResult:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    table_id = str(manifest["table_id"])
    existing = db.query(TableRegistry).filter_by(table_id=table_id).first()
    target_tenant = str(
        tenant_id or manifest.get("tenant_id") or settings.DEFAULT_TENANT_ID
    )
    if existing and existing.tenant_id != target_tenant:
        raise ValueError(
            f"table_id {table_id} already exists in tenant {existing.tenant_id}; "
            f"cannot import into tenant {target_tenant}"
        )
    if existing and not replace:
        return "skipped"

    parquet_path = manifest_path.with_name("data.parquet")
    now = datetime.now(timezone.utc)
    uploaded_at = _parse_datetime(manifest.get("uploaded_at"))
    status = str(manifest.get("status") or default_status)
    source_system = str(
        manifest.get("source_system") or manifest.get("source") or "bulk"
    )
    source_uri = str(manifest.get("source_uri") or parquet_path)

    if existing:
        table = existing
        result: ImportResult = "updated"
    else:
        table = TableRegistry(table_id=table_id)
        db.add(table)
        result = "created"

    table.tenant_id = target_tenant
    table.source_system = source_system
    table.source_uri = source_uri
    table.table_name = str(manifest["table_name"])
    table.row_count = int(manifest.get("row_count") or 0)
    table.col_count = int(manifest.get("col_count") or len(manifest.get("columns", [])))
    table.schema_hash = manifest.get("schema_hash")
    table.content_hash = manifest.get("content_hash")
    table.uploaded_by = manifest.get("uploaded_by")
    table.uploaded_at = uploaded_at
    table.updated_at = now
    table.status = status

    db.query(ColumnMetadata).filter_by(table_id=table_id).delete()
    for column in manifest.get("columns", []):
        col_name = str(column.get("col_name") or column["name"])
        db.add(
            ColumnMetadata(
                column_id=_column_id(table_id, column),
                table_id=table_id,
                ordinal=int(column["ordinal"]),
                col_name=col_name,
                col_type=str(column.get("col_type") or column.get("type") or "str"),
                col_description=column.get("col_description")
                or column.get("description"),
            )
        )

    db.commit()
    return result


def import_manifests(
    root: Path,
    *,
    default_status: str = "INGESTED",
    replace: bool = False,
    tenant_id: str | None = None,
) -> dict[str, int]:
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    summary = {"created": 0, "updated": 0, "skipped": 0}
    with SessionFactory() as db:
        for manifest_path in sorted(root.rglob("manifest.json")):
            result = import_manifest(
                db,
                manifest_path,
                default_status=default_status,
                replace=replace,
                tenant_id=tenant_id,
            )
            summary[result] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Directory containing prepared manifest.json files"
    )
    parser.add_argument(
        "--status",
        default="INGESTED",
        help="Status for manifests without explicit status",
    )
    parser.add_argument(
        "--replace", action="store_true", help="Update existing table rows"
    )
    parser.add_argument(
        "--tenant-id", help="Override manifest tenant_id for all imported tables"
    )
    args = parser.parse_args()

    summary = import_manifests(
        args.root,
        default_status=args.status,
        replace=args.replace,
        tenant_id=args.tenant_id,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
