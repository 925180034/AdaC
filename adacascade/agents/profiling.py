"""ProfilingAgent — feature extraction, SBERT encoding, Qdrant upsert.

Implements Algorithm Spec §2. Called both:
- Offline (BackgroundTasks after POST /tables)
- Online (as a LangGraph node within /integrate, /discover, /match)
"""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from adacascade.artifacts import save_pkl
from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, TableRegistry
from adacascade.indexing.qdrant_client import AdacQdrantClient

log = structlog.get_logger(__name__)

# ── Lazy singleton SBERT model ────────────────────────────────────────────────
_sbert: SentenceTransformer | None = None


def _get_sbert() -> SentenceTransformer:
    global _sbert
    if _sbert is None:
        cfg = settings.profiling_cfg
        model_name = cfg.get("sbert_model", settings.SBERT_MODEL)
        device = cfg.get("sbert_device", settings.SBERT_DEVICE)
        _sbert = SentenceTransformer(model_name, device=device)
    return _sbert


# ── TF-IDF singleton (lazy load from disk) ───────────────────────────────────
_tfidf: TfidfVectorizer | None = None
_TFIDF_PATH = Path(settings.ARTIFACTS_DIR) / "tfidf.pkl"


def _get_tfidf() -> TfidfVectorizer | None:
    global _tfidf
    if _tfidf is None and _TFIDF_PATH.exists():
        with _TFIDF_PATH.open("rb") as f:
            _tfidf = pickle.load(f)
    return _tfidf


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class NumericStats:
    """Descriptive statistics for int/float/date columns."""

    mean: float
    std: float
    q25: float
    q50: float
    q75: float


@dataclass
class CatStats:
    """Frequency statistics for str/bool columns."""

    top_k: list[tuple[str, float]]  # [(value, norm_freq), ...]
    freq_vector_ref: str  # path to pkl with sparse freq vector


@dataclass
class ColumnProfile:
    """Per-column feature profile (Algorithm Spec §2.1)."""

    col_id: str
    ordinal: int
    name: str
    dtype: str
    description: str | None
    null_ratio: float
    distinct_ratio: float
    numeric_stats: NumericStats | None
    categorical_stats: CatStats | None
    col_emb_ref: str  # Qdrant point id
    sample_values: list[str]


@dataclass
class TableProfile:
    """Table-level feature profile (Algorithm Spec §2.1)."""

    table_id: str
    text_blob: str
    tfidf_vec_ref: str  # path to pkl with sparse tfidf vector
    table_emb_ref: str  # Qdrant point id (== table_id)
    type_multiset: list[str]
    columns: list[ColumnProfile] = field(default_factory=list)


# ── Text helpers ──────────────────────────────────────────────────────────────


def _build_text_blob(table_name: str, columns: list[dict[str, Any]]) -> str:
    """Concatenate table name + column names + descriptions (Algorithm Spec §2.2)."""
    parts = [table_name]
    for col in columns:
        parts.append(col["col_name"])
        if col.get("col_description"):
            parts.append(col["col_description"])
    return " ".join(parts).lower()


def _table_sbert_input(table_name: str, col_rows: list[ColumnMetadata]) -> str:
    """Build SBERT input text for the table-level embedding (Algorithm Spec §2.3)."""
    col_parts = ", ".join(
        f"{c.col_name} ({c.col_type})"
        + (f" - {c.col_description}" if c.col_description else "")
        for c in col_rows
    )
    return f"Table: {table_name}. Columns: {col_parts}"


def _col_sbert_input(col: ColumnMetadata, table_name: str) -> str:
    """Build SBERT input text for a column-level embedding (Algorithm Spec §2.3)."""
    text = f"Column {col.col_name} of type {col.col_type}"
    if col.col_description:
        text += f". Description: {col.col_description}"
    text += f". In table {table_name}."
    return text


# ── Statistical feature computation ──────────────────────────────────────────


def _compute_numeric_stats(series: pd.Series) -> NumericStats:
    """Compute mean/std/quartiles (Algorithm Spec §2.4)."""
    vals = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    q25, q50, q75 = (
        np.percentile(vals, [25, 50, 75], method="linear")
        if len(vals)
        else (0.0, 0.0, 0.0)
    )
    return NumericStats(
        mean=float(vals.mean()) if len(vals) else 0.0,
        std=float(vals.std()) if len(vals) else 0.0,
        q25=float(q25),
        q50=float(q50),
        q75=float(q75),
    )


def _compute_cat_stats(series: pd.Series, table_id: str, col_id: str) -> CatStats:
    """Compute top-20 value frequencies (Algorithm Spec §2.4)."""
    vc = series.dropna().astype(str).value_counts()
    total = len(series)
    top_k: list[tuple[str, float]] = [
        (str(v), float(cnt) / total) for v, cnt in vc.head(20).items()
    ]
    # Persist freq vector for Sim_dist (col embedding for category matching)
    freq_vec = {str(v): float(cnt) / total for v, cnt in vc.items()}
    ref = save_pkl(table_id, f"freq_{col_id}", freq_vec)
    return CatStats(top_k=top_k, freq_vector_ref=ref)


# ── Core profile function ─────────────────────────────────────────────────────


def profile_table(
    *,
    table_id: str,
    parquet_path: str,
    db: Session,
) -> TableProfile:
    """Extract features from a Parquet table and return a TableProfile.

    Does NOT upsert to Qdrant (caller handles that after encoding).

    Args:
        table_id: UUID of the table in table_registry.
        parquet_path: Path to the Parquet file on disk.
        db: SQLAlchemy session for reading column_metadata rows.

    Returns:
        Populated TableProfile dataclass.
    """
    cfg = settings.profiling_cfg
    sample_rows: int = cfg.get("sample_rows", 10000)
    sample_values: int = cfg.get("sample_values", 5)

    tr = db.query(TableRegistry).filter_by(table_id=table_id).one()
    col_rows: list[ColumnMetadata] = (
        db.query(ColumnMetadata)
        .filter_by(table_id=table_id)
        .order_by(ColumnMetadata.ordinal)
        .all()
    )

    df = pd.read_parquet(parquet_path)
    if len(df) > sample_rows:
        df = df.sample(sample_rows, random_state=42)

    col_dicts = [
        {
            "col_name": c.col_name,
            "col_type": c.col_type,
            "col_description": c.col_description,
        }
        for c in col_rows
    ]
    text_blob = _build_text_blob(tr.table_name, col_dicts)

    # TF-IDF sparse vector (if vectorizer is trained)
    tfidf_ref = ""
    tfidf = _get_tfidf()
    if tfidf is not None:
        vec = tfidf.transform([text_blob])
        tfidf_ref = save_pkl(table_id, "tfidf_vec", vec)

    col_profiles: list[ColumnProfile] = []
    for col_row in col_rows:
        col_name = col_row.col_name
        col_id = col_row.column_id
        dtype = col_row.col_type

        series = df[col_name] if col_name in df.columns else pd.Series(dtype=object)
        null_ratio = float(series.isna().mean()) if len(series) else 1.0
        distinct_ratio = float(series.nunique() / len(series)) if len(series) else 0.0

        numeric_stats: NumericStats | None = None
        cat_stats: CatStats | None = None

        if dtype in {"int", "float", "date"}:
            numeric_stats = _compute_numeric_stats(series)
        elif dtype in {"str", "bool"}:
            cat_stats = _compute_cat_stats(series, table_id, col_id)

        sample_vals = [str(v) for v in series.dropna().head(sample_values).tolist()]

        col_profiles.append(
            ColumnProfile(
                col_id=col_id,
                ordinal=col_row.ordinal,
                name=col_name,
                dtype=dtype,
                description=col_row.col_description,
                null_ratio=null_ratio,
                distinct_ratio=distinct_ratio,
                numeric_stats=numeric_stats,
                categorical_stats=cat_stats,
                col_emb_ref=col_id,  # Qdrant point id = column_id
                sample_values=sample_vals,
            )
        )

    return TableProfile(
        table_id=table_id,
        text_blob=text_blob,
        tfidf_vec_ref=tfidf_ref,
        table_emb_ref=table_id,  # Qdrant point id = table_id
        type_multiset=[c.col_type for c in col_rows],
        columns=col_profiles,
    )


# ── SBERT encoding + Qdrant upsert ────────────────────────────────────────────


async def encode_and_index(
    *,
    profile: TableProfile,
    db: Session,
    qdrant: AdacQdrantClient,
    tenant_id: str,
) -> None:
    """SBERT-encode table & columns and upsert into Qdrant.

    Updates qdrant_point_id in column_metadata rows.

    Args:
        profile: TableProfile from profile_table().
        db: SQLAlchemy session.
        qdrant: AdacQdrantClient instance.
        tenant_id: Tenant namespace.
    """
    cfg = settings.profiling_cfg
    batch_size: int = cfg.get("sbert_batch_size", 256)

    sbert = _get_sbert()
    tr = db.query(TableRegistry).filter_by(table_id=profile.table_id).one()
    col_rows: list[ColumnMetadata] = (
        db.query(ColumnMetadata)
        .filter_by(table_id=profile.table_id)
        .order_by(ColumnMetadata.ordinal)
        .all()
    )

    # ── Table-level embedding ─────────────────────────────────────────────────
    table_text = _table_sbert_input(tr.table_name, col_rows)
    table_vec: list[float] = sbert.encode(
        [table_text],
        batch_size=batch_size,
        normalize_embeddings=True,
    )[0].tolist()

    await qdrant.upsert_table(
        table_id=profile.table_id,
        tenant_id=tenant_id,
        vector=table_vec,
        extra_payload={"table_name": tr.table_name},
    )

    # ── Column-level embeddings ───────────────────────────────────────────────
    col_texts = [_col_sbert_input(c, tr.table_name) for c in col_rows]
    col_vecs = sbert.encode(
        col_texts,
        batch_size=batch_size,
        normalize_embeddings=True,
    )

    points = [
        {
            "column_id": col_row.column_id,
            "table_id": profile.table_id,
            "tenant_id": tenant_id,
            "vector": col_vecs[i].tolist(),
            "col_type": col_row.col_type,
        }
        for i, col_row in enumerate(col_rows)
    ]
    await qdrant.upsert_columns(points=points)

    # Update qdrant_point_id in DB
    for col_row in col_rows:
        col_row.qdrant_point_id = col_row.column_id
    db.commit()


# ── Background-task entry point ───────────────────────────────────────────────


async def run_profiling(
    *,
    table_id: str,
    db: Session,
    qdrant: AdacQdrantClient,
    tenant_id: str,
) -> None:
    """Full Profiling pipeline: INGESTED → PROFILING → READY (or FAILED).

    Args:
        table_id: Target table.
        db: SQLAlchemy session.
        qdrant: AdacQdrantClient instance.
        tenant_id: Tenant namespace.
    """
    bound_log = log.bind(table_id=table_id)

    # Optimistic lock: only proceed if still INGESTED
    rows_updated = (
        db.query(TableRegistry)
        .filter(TableRegistry.table_id == table_id, TableRegistry.status == "INGESTED")
        .update({"status": "PROFILING", "updated_at": datetime.now(timezone.utc)})
    )
    db.commit()
    if rows_updated == 0:
        bound_log.info("profiling.skip", reason="not INGESTED")
        return

    try:
        tr = db.query(TableRegistry).filter_by(table_id=table_id).one()
        profile = profile_table(
            table_id=table_id,
            parquet_path=tr.source_uri,
            db=db,
        )

        # Persist stat summaries to column_metadata
        for cp in profile.columns:
            stat: dict[str, Any] = {}
            if cp.numeric_stats:
                stat["numeric"] = asdict(cp.numeric_stats)
            if cp.categorical_stats:
                stat["cat_top_k"] = cp.categorical_stats.top_k
                stat["cat_freq_ref"] = cp.categorical_stats.freq_vector_ref
            if stat:
                db.query(ColumnMetadata).filter_by(column_id=cp.col_id).update(
                    {
                        "null_ratio": cp.null_ratio,
                        "distinct_ratio": cp.distinct_ratio,
                        "stat_summary": json.dumps(stat),
                    }
                )

        await encode_and_index(
            profile=profile,
            db=db,
            qdrant=qdrant,
            tenant_id=tenant_id,
        )

        db.query(TableRegistry).filter_by(table_id=table_id).update(
            {"status": "READY", "updated_at": datetime.now(timezone.utc)}
        )
        db.commit()
        bound_log.info("profiling.done", status="READY")

    except Exception:
        db.rollback()
        db.query(TableRegistry).filter_by(table_id=table_id).update(
            {"status": "FAILED", "updated_at": datetime.now(timezone.utc)}
        )
        db.commit()
        bound_log.exception("profiling.failed")
        raise


# ── LangGraph node stubs ──────────────────────────────────────────────────────


async def run_pool(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: profile query table against pool (INTEGRATE/DISCOVER)."""
    # M1: stub — actual implementation in M2
    return {**state, "query_profile": {"table_id": state.get("task_id", "")}}


async def run_pair(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: profile source + target pair (MATCH_ONLY)."""
    # M1: stub — actual implementation in M2
    return {**state, "query_profile": {}, "target_profile": {}}
