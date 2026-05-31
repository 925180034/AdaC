"""POST /tables, GET /tables/{id}, GET /tables, DELETE /tables/{id}."""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Generator

import numpy as np
import pandas as pd
import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi import File as FastAPIFile
from fastapi import Form
from sqlalchemy.orm import Session

from adacascade.api.middleware import get_tenant_id
from adacascade.config import settings
from adacascade.db.models import TableRegistry
from adacascade.db.session import get_session
from adacascade.ingest.pipeline import ingest_table

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/tables", tags=["tables"])


# ── DB dependency ─────────────────────────────────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session from the module-level singleton."""
    with get_session() as db:
        yield db


# ── Helpers ───────────────────────────────────────────────────────────────────


def _table_to_dict(tr: TableRegistry) -> dict[str, Any]:
    return {
        "table_id": tr.table_id,
        "table_name": tr.table_name,
        "tenant_id": tr.tenant_id,
        "dataset_id": tr.dataset_id,
        "status": tr.status,
        "row_count": tr.row_count,
        "col_count": tr.col_count,
        "source_system": tr.source_system,
        "uploaded_by": tr.uploaded_by,
        "uploaded_at": tr.uploaded_at.isoformat() if tr.uploaded_at else None,
        "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
    }


def _bound_preview_limit(limit: int) -> int:
    """Clamp table preview row limits to the supported range."""
    return max(1, min(50, limit))


def _json_safe_value(value: Any) -> Any:
    """Convert pandas values to JSON-serializable preview values."""
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe_value(value.item())
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _resolve_table_source_path(source_uri: str | None) -> Path | None:
    if not source_uri:
        return None

    source_path = Path(source_uri)
    if source_path.is_file() or source_path.is_absolute():
        return source_path

    return Path(settings.DATA_DIR).resolve().parent / source_path


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", status_code=202)
async def upload_table(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = FastAPIFile(...),
    table_name: str = Form(...),
    source_system: str = Form(default="upload"),
    tenant_id: str = Form(default=settings.DEFAULT_TENANT_ID),
    dataset_id: str | None = Form(default=None),
    uploaded_by: str | None = Form(default=None),
    col_descriptions: str | None = Form(default=None),  # JSON string
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upload a CSV or Parquet file; trigger background Profiling.

    Returns 202 Accepted with table_id and initial status.
    """
    descriptions: dict[str, str] | None = None
    if col_descriptions:
        try:
            descriptions = json.loads(col_descriptions)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=422, detail=f"col_descriptions is not valid JSON: {e}"
            )

    raw = await file.read()
    if len(raw) > settings.MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds maximum file size")

    active_tenant_id = get_tenant_id(request) or tenant_id
    table_id, status = ingest_table(
        file=io.BytesIO(raw),
        filename=file.filename or "upload",
        table_name=table_name,
        source_system=source_system,
        tenant_id=active_tenant_id,
        dataset_id=dataset_id,
        uploaded_by=uploaded_by,
        col_descriptions=descriptions,
        db=db,
    )
    db.commit()

    if status == "INGESTED":
        qdrant = request.app.state.qdrant

        async def _profiling_task() -> None:
            from adacascade.agents.profiling import run_profiling

            with get_session() as bg_db:
                await run_profiling(
                    table_id=table_id,
                    db=bg_db,
                    qdrant=qdrant,
                    tenant_id=active_tenant_id,
                )

        background_tasks.add_task(_profiling_task)
        log.info("tables.upload", table_id=table_id, status=status)
    else:
        log.info("tables.dedup", table_id=table_id, status=status)

    return {"table_id": table_id, "status": status}


@router.get("/{table_id}/preview")
async def preview_table(
    table_id: str,
    request: Request,
    db: Session = Depends(get_db),
    dataset_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return table metadata and a bounded Parquet row preview."""
    bounded_limit = _bound_preview_limit(limit)
    tr = (
        db.query(TableRegistry)
        .filter_by(table_id=table_id, tenant_id=get_tenant_id(request))
        .first()
    )
    if tr is None or (dataset_id is not None and tr.dataset_id != dataset_id):
        raise HTTPException(status_code=404, detail="Table not found")

    source_path = _resolve_table_source_path(tr.source_uri)
    if source_path is None or not source_path.is_file():
        raise HTTPException(status_code=404, detail="Table data file not found")

    frame = pd.read_parquet(source_path).head(bounded_limit)
    rows = [
        {str(column): _json_safe_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    return {
        "table": _table_to_dict(tr),
        "columns": [str(column) for column in frame.columns],
        "sample_rows": rows,
        "sample_limit": bounded_limit,
    }


@router.get("/{table_id}")
async def get_table(
    table_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a table's status and metadata."""
    tr = db.query(TableRegistry).filter_by(table_id=table_id).first()
    if tr is None or tr.tenant_id != get_tenant_id(request):
        raise HTTPException(status_code=404, detail="Table not found")
    return _table_to_dict(tr)


@router.get("")
async def list_tables(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str | None = None,
    status: str | None = None,
    dataset_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List tables with optional tenant/status/Dataset filtering."""
    q = db.query(TableRegistry)
    q = q.filter_by(tenant_id=tenant_id or get_tenant_id(request))
    if status:
        q = q.filter_by(status=status)
    if dataset_id:
        q = q.filter_by(dataset_id=dataset_id)
    total = q.count()
    rows = (
        q.order_by(TableRegistry.uploaded_at.desc()).offset(offset).limit(limit).all()
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_table_to_dict(r) for r in rows],
    }


@router.delete("/{table_id}", status_code=200)
async def delete_table(
    table_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Soft-delete a table: set ARCHIVED + hard-delete Qdrant vectors."""
    tr = db.query(TableRegistry).filter_by(table_id=table_id).first()
    if tr is None or tr.tenant_id != get_tenant_id(request):
        raise HTTPException(status_code=404, detail="Table not found")
    if tr.status == "ARCHIVED":
        return {"table_id": table_id, "status": "ARCHIVED"}

    tr.status = "ARCHIVED"
    tr.updated_at = datetime.now(timezone.utc)

    qdrant = request.app.state.qdrant
    await qdrant.delete_table(table_id=table_id)

    log.info("tables.delete", table_id=table_id)
    return {"table_id": table_id, "status": "ARCHIVED"}
