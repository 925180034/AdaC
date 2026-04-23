"""POST /tables, GET /tables/{id}, GET /tables, DELETE /tables/{id}."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Generator

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi import File as FastAPIFile
from fastapi import Form
from sqlalchemy.orm import Session

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
        "status": tr.status,
        "row_count": tr.row_count,
        "col_count": tr.col_count,
        "source_system": tr.source_system,
        "uploaded_by": tr.uploaded_by,
        "uploaded_at": tr.uploaded_at.isoformat() if tr.uploaded_at else None,
        "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", status_code=202)
async def upload_table(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = FastAPIFile(...),
    table_name: str = Form(...),
    source_system: str = Form(default="upload"),
    tenant_id: str = Form(default=settings.DEFAULT_TENANT_ID),
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
            raise HTTPException(status_code=422, detail=f"col_descriptions is not valid JSON: {e}")

    raw = await file.read()

    table_id, status = ingest_table(
        file=io.BytesIO(raw),
        filename=file.filename or "upload",
        table_name=table_name,
        source_system=source_system,
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
        col_descriptions=descriptions,
        db=db,
    )

    if status == "INGESTED":
        qdrant = request.app.state.qdrant

        async def _profiling_task() -> None:
            from adacascade.agents.profiling import run_profiling

            with get_session() as bg_db:
                await run_profiling(
                    table_id=table_id,
                    db=bg_db,
                    qdrant=qdrant,
                    tenant_id=tenant_id,
                )

        background_tasks.add_task(_profiling_task)
        log.info("tables.upload", table_id=table_id, status=status)
    else:
        log.info("tables.dedup", table_id=table_id, status=status)

    return {"table_id": table_id, "status": status}


@router.get("/{table_id}")
async def get_table(
    table_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a table's status and metadata."""
    tr = db.query(TableRegistry).filter_by(table_id=table_id).first()
    if tr is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return _table_to_dict(tr)


@router.get("")
async def list_tables(
    db: Session = Depends(get_db),
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List tables with optional tenant/status filtering."""
    q = db.query(TableRegistry)
    if tenant_id:
        q = q.filter_by(tenant_id=tenant_id)
    if status:
        q = q.filter_by(status=status)
    total = q.count()
    rows = q.order_by(TableRegistry.uploaded_at.desc()).offset(offset).limit(limit).all()
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
    if tr is None:
        raise HTTPException(status_code=404, detail="Table not found")
    if tr.status == "ARCHIVED":
        return {"table_id": table_id, "status": "ARCHIVED"}

    tr.status = "ARCHIVED"
    tr.updated_at = datetime.now(timezone.utc)

    qdrant = request.app.state.qdrant
    await qdrant.delete_table(table_id=table_id)

    log.info("tables.delete", table_id=table_id)
    return {"table_id": table_id, "status": "ARCHIVED"}
