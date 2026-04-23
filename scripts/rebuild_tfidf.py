#!/usr/bin/env python
"""Train TF-IDF vectorizer on all READY tables and save to data/artifacts/tfidf.pkl.

Run after bulk ingest. Re-run when cumulative table count grows >= 50%.
Usage: python scripts/rebuild_tfidf.py
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

# Allow running as a script without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, TableRegistry

ARTIFACTS_DIR = Path(settings.ARTIFACTS_DIR)
TFIDF_PATH = ARTIFACTS_DIR / "tfidf.pkl"


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        tables = db.query(TableRegistry).filter_by(status="READY").all()
        if not tables:
            print("[rebuild_tfidf] No READY tables found. Exiting.")
            return

        blobs: list[str] = []
        for tr in tables:
            col_rows = (
                db.query(ColumnMetadata)
                .filter_by(table_id=tr.table_id)
                .order_by(ColumnMetadata.ordinal)
                .all()
            )
            parts = [tr.table_name]
            for c in col_rows:
                parts.append(c.col_name)
                if c.col_description:
                    parts.append(c.col_description)
            blobs.append(" ".join(parts).lower())

        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

        # min_df=2 requires the corpus to be large enough that max_df=0.9 still
        # allows at least 2 documents (i.e. int(0.9 * n) >= 2, so n >= 3).
        # With very small corpora fall back to min_df=1 to avoid a ValueError.
        effective_min_df = 2 if len(blobs) >= 3 else 1
        vec = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"(?u)\b\w+\b",
            ngram_range=(1, 1),
            min_df=effective_min_df,
            max_df=0.9,
            sublinear_tf=True,
        )
        vec.fit(blobs)

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        with TFIDF_PATH.open("wb") as f:
            pickle.dump(vec, f)

        print(f"[rebuild_tfidf] Trained on {len(blobs)} tables. Saved to {TFIDF_PATH}")
        print(f"[rebuild_tfidf] Vocabulary size: {len(vec.vocabulary_)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
