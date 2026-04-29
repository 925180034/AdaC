#!/usr/bin/env python3
"""Garbage-collect ARCHIVED table metadata and local table files."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.config import settings
from adacascade.db.models import Base, TableRegistry


def _table_dir(data_dir: Path, table: TableRegistry) -> Path:
    source_path = Path(table.source_uri)
    if source_path.name == "data.parquet":
        return source_path.parent
    return data_dir / "tables" / table.tenant_id / table.table_id


def garbage_collect(db: Session, *, data_dir: Path) -> dict[str, int]:
    archived = db.query(TableRegistry).filter_by(status="ARCHIVED").all()
    summary = {"scanned": len(archived), "deleted_records": 0, "deleted_dirs": 0}
    data_root = data_dir.resolve()

    for table in archived:
        table_dir = _table_dir(data_dir, table)
        if table_dir.exists() and table_dir.resolve().is_relative_to(data_root):
            shutil.rmtree(table_dir)
            summary["deleted_dirs"] += 1
        db.delete(table)
        summary["deleted_records"] += 1

    db.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(settings.DATA_DIR))
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    with SessionFactory() as db:
        summary = garbage_collect(db, data_dir=args.data_dir)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
