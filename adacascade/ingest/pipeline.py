"""Ingest pipeline: PENDING → INGESTED state transition.

Validates format, converts to Parquet, computes schema_hash and content_hash,
persists to data/tables/{tenant_id}/{table_id}/, and writes table_registry row.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Iterable
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import IO, Any

import pandas as pd
from sqlalchemy.orm import Session

from adacascade.config import settings
from adacascade.db.models import ColumnMetadata, DatasetRegistry, TableRegistry


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
    suffix = Path(filename).suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(io.BytesIO(raw))
    if suffix != ".csv":
        raise ValueError(f"Unsupported file format: {filename}")
    # CSV with encoding fallback
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            _validate_csv_header(raw, enc)
            return pd.read_csv(io.BytesIO(raw), encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Cannot decode {filename} as CSV (tried utf-8, utf-8-sig, latin-1)"
    )


def _validate_csv_header(raw: bytes, encoding: str) -> None:
    """Validate the original CSV header before pandas mangles column names."""
    text = raw.decode(encoding)
    rows = csv.reader(io.StringIO(text))
    try:
        header = next(rows)
    except StopIteration as exc:
        raise ValueError("table must contain at least one column") from exc
    normalized_header = [column.strip() for column in header]
    for column in normalized_header:
        if column == "":
            raise ValueError("blank column name")
    seen: set[str] = set()
    for column in normalized_header:
        if column in seen:
            raise ValueError(f"duplicate column name: {column}")
        seen.add(column)


def _validate_and_normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Validate non-empty tabular data and trim column names."""
    if len(df.index) == 0:
        raise ValueError("table must contain at least one data row")
    normalized_columns = [str(column).strip() for column in df.columns]
    for column in normalized_columns:
        if column == "":
            raise ValueError("blank column name")
    seen: set[str] = set()
    for column in normalized_columns:
        if column in seen:
            raise ValueError(f"duplicate column name: {column}")
        seen.add(column)
    normalized = df.copy()
    normalized.columns = normalized_columns
    if len(normalized.columns) == 0:
        raise ValueError("table must contain at least one column")
    return normalized


def _table_name_from_source(source: str, prefix: str | None) -> str:
    """Build a stable table name from an upload source path."""
    stem = Path(source).stem.strip()
    return f"{prefix}_{stem}" if prefix else stem


def _is_supported_table_file(filename: str) -> bool:
    """Return whether the upload can be ingested as a table file."""
    return Path(filename).suffix.lower() in {".csv", ".parquet", ".xlsx"}


def _is_hidden_or_macosx(path: PurePosixPath) -> bool:
    """Return whether a ZIP member should be ignored as platform metadata."""
    return any(part.startswith(".") or part == "__MACOSX" for part in path.parts)


def _iter_upload_members(filename: str, payload: bytes) -> Iterable[tuple[str, bytes]]:
    """Yield concrete table files from a direct upload or a shallow ZIP archive."""
    if Path(filename).suffix.lower() != ".zip":
        yield filename, payload
        return

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            source_path = PurePosixPath(info.filename)
            parts = [part for part in source_path.parts if part not in {"", "."}]
            if info.is_dir() or len(parts) == 0:
                continue
            if _is_hidden_or_macosx(source_path):
                continue
            if len(parts) > 2:
                continue
            if not _is_supported_table_file(parts[-1]):
                continue
            yield info.filename, archive.read(info)


def _skip_reason(filename: str) -> str | None:
    """Return skip reason for unsupported ZIP member, or None if ingestible."""
    source_path = PurePosixPath(filename)
    parts = [part for part in source_path.parts if part not in {"", "."}]
    if len(parts) == 0:
        return "empty path"
    if _is_hidden_or_macosx(source_path):
        return "hidden or metadata file"
    if len(parts) > 2:
        return "nested deeper than one directory"
    if not _is_supported_table_file(parts[-1]):
        return "unsupported file type"
    return None


def _ensure_dataset(
    *, db: Session, tenant_id: str, dataset_id: str, uploaded_by: str | None
) -> None:
    """Create a dataset registry row if one does not already exist."""
    existing = db.query(DatasetRegistry).filter_by(dataset_id=dataset_id).first()
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.updated_at = now
        return
    db.add(
        DatasetRegistry(
            dataset_id=dataset_id,
            tenant_id=tenant_id,
            dataset_name=dataset_id,
            description=None,
            created_by=uploaded_by,
            created_at=now,
            updated_at=now,
            status="ACTIVE",
            is_system=False,
        )
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
    dataset_id: str | None = None,
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

    df = _validate_and_normalize_schema(_read_upload(io.BytesIO(raw_bytes), filename))

    s_hash = _schema_hash(df)
    c_hash = _content_hash(raw_bytes)

    # ── Dedup check ──────────────────────────────────────────────────────────
    duplicate_filters: dict[str, str | None] = {
        "tenant_id": tenant_id,
        "content_hash": c_hash,
    }
    if dataset_id is not None:
        duplicate_filters["dataset_id"] = dataset_id
    existing = db.query(TableRegistry).filter_by(**duplicate_filters).first()
    if existing:
        return existing.table_id, "REJECTED"

    table_id = _stable_id(f"{tenant_id}:{dataset_id or ''}:{table_name}:{c_hash}")
    now = datetime.now(timezone.utc)
    if dataset_id is not None:
        _ensure_dataset(
            db=db, tenant_id=tenant_id, dataset_id=dataset_id, uploaded_by=uploaded_by
        )

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
        "dataset_id": dataset_id,
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
        dataset_id=dataset_id,
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


def ingest_upload_bundle(
    *,
    files: list[tuple[str, bytes]],
    tenant_id: str,
    dataset_id: str,
    uploaded_by: str | None,
    table_name_prefix: str | None,
    db: Session,
) -> dict[str, Any]:
    """Ingest uploaded CSV, Parquet, Excel, or ZIP files into one dataset.

    Args:
        files: Sequence of ``(filename, bytes)`` uploaded by the caller.
        tenant_id: Tenant namespace.
        dataset_id: Dataset namespace used for duplicate scoping.
        uploaded_by: Username or API client identifier.
        table_name_prefix: Optional prefix prepended to derived table names.
        db: SQLAlchemy session; this function flushes but does not commit.

    Returns:
        Summary with accepted, rejected, and skipped entries.
    """
    _ensure_dataset(db=db, tenant_id=tenant_id, dataset_id=dataset_id, uploaded_by=uploaded_by)
    summary: dict[str, Any] = {
        "dataset_id": dataset_id,
        "accepted": [],
        "rejected": [],
        "skipped": [],
    }

    for filename, payload in files:
        if Path(filename).suffix.lower() == ".zip":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = [info for info in archive.infolist() if not info.is_dir()]
                if len(members) > settings.MAX_ZIP_MEMBER_COUNT:
                    summary["rejected"].append(
                        {
                            "source": filename,
                            "reason": f"zip contains more than {settings.MAX_ZIP_MEMBER_COUNT} files",
                        }
                    )
                    continue
                uncompressed = sum(info.file_size for info in members)
                if uncompressed > settings.MAX_ZIP_UNCOMPRESSED_BYTES:
                    summary["rejected"].append(
                        {"source": filename, "reason": "zip uncompressed size exceeds limit"}
                    )
                    continue
                for info in members:
                    reason = _skip_reason(info.filename)
                    if reason is not None:
                        summary["skipped"].append(
                            {"source": info.filename, "reason": reason}
                        )
                        continue
                    _ingest_bundle_member(
                        source=info.filename,
                        payload=archive.read(info),
                        tenant_id=tenant_id,
                        dataset_id=dataset_id,
                        uploaded_by=uploaded_by,
                        table_name_prefix=table_name_prefix,
                        db=db,
                        summary=summary,
                    )
            continue

        if not _is_supported_table_file(filename):
            summary["skipped"].append(
                {"source": filename, "reason": "unsupported file type"}
            )
            continue
        _ingest_bundle_member(
            source=filename,
            payload=payload,
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            uploaded_by=uploaded_by,
            table_name_prefix=table_name_prefix,
            db=db,
            summary=summary,
        )

    return summary


def _ingest_bundle_member(
    *,
    source: str,
    payload: bytes,
    tenant_id: str,
    dataset_id: str,
    uploaded_by: str | None,
    table_name_prefix: str | None,
    db: Session,
    summary: dict[str, Any],
) -> None:
    """Ingest one table-like bundle member and update summary in place."""
    suffix = Path(source).suffix.lower()
    if suffix == ".xlsx":
        try:
            sheets = pd.read_excel(io.BytesIO(payload), sheet_name=None)
        except ImportError as exc:
            raise ValueError("Excel ingestion requires openpyxl") from exc
        if len(sheets) > settings.MAX_EXCEL_SHEETS:
            summary["rejected"].append(
                {
                    "source": source,
                    "reason": f"excel workbook contains more than {settings.MAX_EXCEL_SHEETS} sheets",
                }
            )
            return
        for sheet_name, frame in sheets.items():
            try:
                normalized = _validate_and_normalize_schema(frame)
                table_name = f"{Path(source).stem}__{sheet_name}"
                if table_name_prefix:
                    table_name = f"{table_name_prefix}_{table_name}"
                sheet_payload = normalized.to_csv(index=False).encode("utf-8")
                table_id, status = ingest_table(
                    file=io.BytesIO(sheet_payload),
                    filename=f"{Path(source).stem}__{sheet_name}.csv",
                    table_name=table_name,
                    source_system="upload",
                    tenant_id=tenant_id,
                    dataset_id=dataset_id,
                    uploaded_by=uploaded_by,
                    col_descriptions=None,
                    db=db,
                )
            except ValueError as exc:
                summary["rejected"].append(
                    {"source": f"{source}:{sheet_name}", "reason": str(exc)}
                )
                continue
            if status == "INGESTED":
                summary["accepted"].append(
                    {"source": f"{source}:{sheet_name}", "table_id": table_id, "table_name": table_name}
                )
            else:
                summary["rejected"].append(
                    {"source": f"{source}:{sheet_name}", "reason": "duplicate content"}
                )
        return

    table_name = _table_name_from_source(PurePosixPath(source).name, table_name_prefix)
    try:
        table_id, status = ingest_table(
            file=io.BytesIO(payload),
            filename=source,
            table_name=table_name,
            source_system="upload",
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            uploaded_by=uploaded_by,
            col_descriptions=None,
            db=db,
        )
    except ValueError as exc:
        summary["rejected"].append({"source": source, "reason": str(exc)})
        return

    if status == "INGESTED":
        summary["accepted"].append(
            {"source": source, "table_id": table_id, "table_name": table_name}
        )
    else:
        summary["rejected"].append({"source": source, "reason": "duplicate content"})
