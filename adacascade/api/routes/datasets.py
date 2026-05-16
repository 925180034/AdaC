"""Dataset management and Dataset-scoped uploads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generator
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi import File as FastAPIFile
from fastapi import Form
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from adacascade.api.middleware import get_tenant_id
from adacascade.db.models import DatasetRegistry, TableRegistry
from adacascade.db.session import get_session
from adacascade.ingest.pipeline import ingest_upload_bundle

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/datasets", tags=["datasets"])


class CreateDatasetRequest(BaseModel):
    """Request body for creating a Dataset."""

    dataset_name: str
    description: str | None = None
    created_by: str | None = None


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session from the module-level singleton."""
    with get_session() as db:
        yield db


def _dataset_to_dict(dataset: DatasetRegistry, counts: dict[str, dict[str, int]] | None = None) -> dict[str, Any]:
    dataset_counts = counts.get(dataset.dataset_id, {}) if counts else {}
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset_name,
        "description": dataset.description,
        "is_system": dataset.is_system,
        "table_count": dataset_counts.get("table_count", 0),
        "ready_count": dataset_counts.get("ready_count", 0),
        "failed_count": dataset_counts.get("failed_count", 0),
        "created_at": dataset.created_at.isoformat(),
        "updated_at": dataset.updated_at.isoformat(),
    }


def _table_counts(db: Session, tenant_id: str) -> dict[str, dict[str, int]]:
    rows = (
        db.query(
            TableRegistry.dataset_id,
            func.count(TableRegistry.table_id),
            func.sum(case((TableRegistry.status == "READY", 1), else_=0)),
            func.sum(case((TableRegistry.status == "FAILED", 1), else_=0)),
        )
        .filter(TableRegistry.tenant_id == tenant_id, TableRegistry.dataset_id.isnot(None))
        .group_by(TableRegistry.dataset_id)
        .all()
    )
    return {
        str(dataset_id): {
            "table_count": int(table_count or 0),
            "ready_count": int(ready_count or 0),
            "failed_count": int(failed_count or 0),
        }
        for dataset_id, table_count, ready_count, failed_count in rows
    }


@router.get("")
async def list_datasets(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    """List active Datasets for the current tenant."""
    tenant_id = get_tenant_id(request)
    datasets = (
        db.query(DatasetRegistry)
        .filter_by(tenant_id=tenant_id, status="ACTIVE")
        .order_by(DatasetRegistry.updated_at.desc(), DatasetRegistry.dataset_name)
        .all()
    )
    counts = _table_counts(db, tenant_id)
    return {"items": [_dataset_to_dict(dataset, counts) for dataset in datasets]}


@router.post("", status_code=201)
async def create_dataset(
    body: CreateDatasetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a tenant-scoped Dataset."""
    tenant_id = get_tenant_id(request)
    dataset_name = body.dataset_name.strip()
    if not dataset_name:
        raise HTTPException(status_code=422, detail="dataset_name must not be blank")
    now = datetime.now(timezone.utc)
    dataset = DatasetRegistry(
        dataset_id=str(uuid4()),
        tenant_id=tenant_id,
        dataset_name=dataset_name,
        description=body.description,
        created_by=body.created_by,
        created_at=now,
        updated_at=now,
        status="ACTIVE",
        is_system=False,
    )
    db.add(dataset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Dataset name already exists") from exc
    return _dataset_to_dict(dataset)


@router.post("/{dataset_id}/tables", status_code=202)
async def upload_dataset_tables(
    dataset_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = FastAPIFile(...),
    uploaded_by: str | None = Form(default=None),
    table_name_prefix: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upload one or more files into a Dataset and schedule profiling."""
    tenant_id = get_tenant_id(request)
    dataset = db.query(DatasetRegistry).filter_by(dataset_id=dataset_id, tenant_id=tenant_id).first()
    if dataset is None or dataset.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.is_system:
        raise HTTPException(status_code=403, detail="System datasets do not accept uploads")

    payloads = [(upload.filename or "upload", await upload.read()) for upload in files]
    summary = ingest_upload_bundle(
        files=payloads,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        uploaded_by=uploaded_by,
        table_name_prefix=table_name_prefix,
        db=db,
    )
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()

    accepted_ids = [str(item["table_id"]) for item in summary["accepted"]]
    if accepted_ids:
        qdrant = request.app.state.qdrant

        async def _profiling_task() -> None:
            from adacascade.agents.profiling import run_profiling

            for table_id in accepted_ids:
                with get_session() as bg_db:
                    await run_profiling(table_id=table_id, db=bg_db, qdrant=qdrant, tenant_id=tenant_id)

        background_tasks.add_task(_profiling_task)
        log.info("datasets.upload", dataset_id=dataset_id, accepted=len(accepted_ids))
    return summary
