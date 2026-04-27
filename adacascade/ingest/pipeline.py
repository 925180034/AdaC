"""Ingest pipeline: PENDING → INGESTED state transition.

Validates format, converts to Parquet, computes schema_hash and content_hash,
persists to data/tables/{tenant_id}/{table_id}/, and writes table_registry row.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

import pandas as pd
from sqlalchemy.orm import Session

from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, TableRegistry


# ── Constants ────────────────────────────────────────────────────────────────

_NAMESPACE = uuid.UUID("adac0000-0000-0000-0000-000000000001")

_DTYPE_MAP: dict[str, str] = {
    "int64": "int",
    "int32": "int",
    "int16": "int",
    "int8": "int",
    "uint64": "int",
    "uint32": "int",
    "uint16": "int",
    "uint8": "int",
    "float64": "float",
    "float32": "float",
    "float16": "float",
    "bool": "bool",
    "object": "str",
    "string": "str",
    "category": "str",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _stable_id(seed: str) -> str:
    """Deterministic UUID5 from seed string."""
    return str(uuid.uuid5(_NAMESPACE, seed))


def _infer_col_type(series: pd.Series) -> str:
    """Map pandas dtype to AdaCascade column type token."""
    dtype_str = str(series.dtype)
    if "datetime" in dtype_str or "timestamp" in dtype_str:
        return "date"
    if dtype_str.startswith("period"):
        return "date"
    return _DTYPE_MAP.get(dtype_str, "str")


def _schema_hash(df: pd.DataFrame) -> str:
    """SHA-256 of column names + types + ordinal order → 16-char hex."""
    parts = [f"{i}:{c}:{_infer_col_type(df[c])}" for i, c in enumerate(df.columns)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _content_hash(data: bytes) -> str:
    """SHA-256 of raw file bytes → 16-char hex."""
    return hashlib.sha256(data).hexdigest()[:16]


def _read_upload(file: IO[bytes], filename: str) -> pd.DataFrame:
    """Parse uploaded file (CSV or Parquet) into a DataFrame."""
    raw = file.read()
    if filename.lower().endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(raw))
    # CSV with encoding fallback
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Cannot decode {filename} as CSV (tried utf-8, utf-8-sig, latin-1)"
    )


# ── Public API ────────────────────────────────────────────────────────────────


def ingest_table(
    *,
    file: IO[bytes],
    filename: str,
    table_name: str,
    source_system: str,
    tenant_id: str,
    uploaded_by: str | None,
    col_descriptions: dict[str, str] | None,
    db: Session,
) -> tuple[str, str]:
    """Run the PENDING → INGESTED transition.

    Args:
        file: Uploaded file-like object (CSV or Parquet).
        filename: Original filename for format detection.
        table_name: Human-readable table name.
        source_system: 'upload' | 'bulk' | 'host_platform'.
        tenant_id: Tenant namespace.
        uploaded_by: Username or API client identifier.
        col_descriptions: Optional {col_name: description} mapping.
        db: SQLAlchemy session (caller manages commit/rollback).

    Returns:
        Tuple of (table_id, status) where status is 'INGESTED' on success
        or 'REJECTED' if the table already exists (same content hash).

    Raises:
        ValueError: On unsupported format or unreadable file.
    """
    raw_bytes = file.read()
    file.seek(0)

    df = _read_upload(io.BytesIO(raw_bytes), filename)

    s_hash = _schema_hash(df)
    c_hash = _content_hash(raw_bytes)

    # ── Dedup check ──────────────────────────────────────────────────────────
    existing = (
        db.query(TableRegistry)
        .filter_by(tenant_id=tenant_id, content_hash=c_hash)
        .first()
    )
    if existing:
        return existing.table_id, "REJECTED"

    table_id = _stable_id(f"{tenant_id}:{table_name}:{c_hash}")
    now = datetime.now(timezone.utc)

    # ── Persist Parquet ──────────────────────────────────────────────────────
    out_dir = Path(settings.DATA_DIR) / "tables" / tenant_id / table_id
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "data.parquet"
    df.to_parquet(parquet_path, index=False)

    source_uri = str(parquet_path)

    # ── Build manifest ────────────────────────────────────────────────────────
    descriptions = col_descriptions or {}
    col_records = []
    for i, col in enumerate(df.columns):
        col_id = _stable_id(f"{table_id}:{i}:{col}")
        col_records.append(
            {
                "column_id": col_id,
                "ordinal": i,
                "col_name": col,
                "col_type": _infer_col_type(df[col]),
                "col_description": descriptions.get(col),
            }
        )

    manifest = {
        "table_id": table_id,
        "table_name": table_name,
        "tenant_id": tenant_id,
        "source_system": source_system,
        "source_uri": source_uri,
        "row_count": int(len(df)),
        "col_count": int(len(df.columns)),
        "schema_hash": s_hash,
        "content_hash": c_hash,
        "uploaded_by": uploaded_by,
        "uploaded_at": now.isoformat(),
        "status": "INGESTED",
        "columns": col_records,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # ── Write DB ──────────────────────────────────────────────────────────────
    table_row = TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        source_system=source_system,
        source_uri=source_uri,
        table_name=table_name,
        row_count=int(len(df)),
        col_count=int(len(df.columns)),
        schema_hash=s_hash,
        content_hash=c_hash,
        uploaded_by=uploaded_by,
        uploaded_at=now,
        updated_at=now,
        status="INGESTED",
    )
    db.add(table_row)

    for rec in col_records:
        db.add(
            ColumnMetadata(
                column_id=rec["column_id"],
                table_id=table_id,
                ordinal=rec["ordinal"],
                col_name=rec["col_name"],
                col_type=rec["col_type"],
                col_description=rec["col_description"],
            )
        )

    return table_id, "INGESTED"
