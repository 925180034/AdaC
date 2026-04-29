#!/usr/bin/env python
"""Train corpus-scoped TF-IDF vectorizers for READY tables."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, TableRegistry

Corpus = Literal["all", "join", "union", "matcher"]
ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)


def _artifact_path(artifacts_dir: Path, tenant_id: str, corpus: Corpus) -> Path:
    if corpus == "all":
        return artifacts_dir / "tfidf.pkl"
    return artifacts_dir / f"tfidf_{tenant_id}_{corpus}.pkl"


def _source_systems(corpus: Corpus) -> list[str] | None:
    if corpus == "join":
        return ["retrieval|join"]
    if corpus == "union":
        return ["retrieval|union"]
    if corpus == "matcher":
        return ["wikidata", "mimic_omop"]
    return None


def _ready_tables(
    db: Session, *, tenant_id: str, corpus: Corpus
) -> list[TableRegistry]:
    query = db.query(TableRegistry).filter_by(tenant_id=tenant_id, status="READY")
    source_systems = _source_systems(corpus)
    if source_systems is not None:
        query = query.filter(TableRegistry.source_system.in_(source_systems))
    return list(query.order_by(TableRegistry.table_name).all())


def _table_blob(db: Session, table: TableRegistry) -> str:
    col_rows = (
        db.query(ColumnMetadata)
        .filter_by(table_id=table.table_id)
        .order_by(ColumnMetadata.ordinal)
        .all()
    )
    parts = [table.table_name]
    for column in col_rows:
        parts.append(column.col_name)
        if column.col_description:
            parts.append(column.col_description)
    return " ".join(parts).lower()


def rebuild_tfidf(
    db: Session,
    *,
    tenant_id: str = settings.DEFAULT_TENANT_ID,
    corpus: Corpus = "all",
    artifacts_dir: Path = ARTIFACTS_DIR,
) -> dict[str, object]:
    tables = _ready_tables(db, tenant_id=tenant_id, corpus=corpus)
    if not tables:
        return {
            "tables": 0,
            "path": str(_artifact_path(artifacts_dir, tenant_id, corpus)),
        }

    blobs = [_table_blob(db, table) for table in tables]

    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

    effective_min_df = 2 if len(blobs) >= 3 else 1
    effective_max_df = 0.9 if len(blobs) >= 3 else 1.0
    vec = TfidfVectorizer(
        lowercase=True,
        token_pattern=r"(?u)\b\w+\b",
        ngram_range=(1, 1),
        min_df=effective_min_df,
        max_df=effective_max_df,
        sublinear_tf=True,
    )
    vec.fit(blobs)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = _artifact_path(artifacts_dir, tenant_id, corpus)
    with path.open("wb") as f:
        pickle.dump(vec, f)

    return {
        "tables": len(blobs),
        "path": str(path),
        "vocabulary_size": len(vec.vocabulary_),
        "vocabulary": dict(vec.vocabulary_),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default=settings.DEFAULT_TENANT_ID)
    parser.add_argument(
        "--corpus", choices=["all", "join", "union", "matcher"], default="all"
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    SessionFactory = sessionmaker(bind=engine)
    with SessionFactory() as db:
        summary = rebuild_tfidf(db, tenant_id=args.tenant_id, corpus=args.corpus)

    if summary["tables"] == 0:
        print("[rebuild_tfidf] No READY tables found. Exiting.")
        return
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
