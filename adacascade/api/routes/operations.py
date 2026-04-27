"""Integration operation endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Generator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adacascade.config import settings
from adacascade.db.models import ColumnMapping, DiscoveryResult, IntegrationTask
from adacascade.db.session import get_session

router = APIRouter(tags=["operations"])


class IntegrateRequest(BaseModel):
    """Request body for /integrate and /discover."""

    query_table_id: str
    tenant_id: str = settings.DEFAULT_TENANT_ID
    options: dict[str, Any] = {}


class MatchRequest(BaseModel):
    """Request body for /match."""

    source_table_id: str
    target_table_id: str
    tenant_id: str = settings.DEFAULT_TENANT_ID
    options: dict[str, Any] = {}


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session from the module-level singleton."""
    with get_session() as db:
        yield db


def _create_task(
    db: Session,
    *,
    task_type: str,
    tenant_id: str,
    query_table_id: str,
    target_table_id: str | None,
    options: dict[str, Any],
) -> IntegrationTask:
    now = datetime.now(timezone.utc)
    task = IntegrationTask(
        task_id=str(uuid4()),
        tenant_id=tenant_id,
        task_type=task_type,
        query_table_id=query_table_id,
        target_table_id=target_table_id,
        plan_config=json.dumps(options),
        status="RUNNING",
        submitted_at=now,
        finished_at=None,
        error_message=None,
        artifacts_dir=None,
    )
    db.add(task)
    db.flush()
    return task


def _persist_success(db: Session, task: IntegrationTask, state: dict[str, Any]) -> None:
    task.status = "SUCCESS"
    task.finished_at = datetime.now(timezone.utc)
    ranking = state.get("ranking", [])
    for idx, item in enumerate(ranking, start=1):
        db.add(
            DiscoveryResult(
                task_id=task.task_id,
                rank=idx,
                candidate_table=str(item["table_id"]),
                score=float(item["score"]),
                layer_scores=json.dumps(item.get("layer_scores", {})),
            )
        )
    for item in state.get("final_mappings", []):
        db.add(
            ColumnMapping(
                mapping_id=str(uuid4()),
                task_id=task.task_id,
                src_column_id=str(item["source_col_id"]),
                tgt_column_id=str(item["target_col_id"]),
                scenario=str(item["scenario"]),
                confidence=float(item["confidence"]),
                is_matched=1,
                reasoning=str(item.get("reasoning", "")),
                created_at=datetime.now(timezone.utc),
            )
        )


def _persist_failure(task: IntegrationTask, exc: Exception) -> None:
    task.status = "FAILED"
    task.finished_at = datetime.now(timezone.utc)
    task.error_message = str(exc)


async def _run_task(
    request: Request,
    db: Session,
    *,
    task_type: str,
    tenant_id: str,
    query_table_id: str,
    target_table_id: str | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    task = _create_task(
        db,
        task_type=task_type,
        tenant_id=tenant_id,
        query_table_id=query_table_id,
        target_table_id=target_table_id,
        options=options,
    )
    initial_state = {
        "task_id": task.task_id,
        "tenant_id": tenant_id,
        "task_type": task_type,
        "query_table_id": query_table_id,
        "target_table_id": target_table_id,
        "plan": options,
        "status": "RUNNING",
        "degraded": False,
    }
    try:
        state = await request.app.state.graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": task.task_id}},
        )
        _persist_success(db, task, state)
        return {"task_id": task.task_id, "status": task.status, "state": state}
    except Exception as exc:
        _persist_failure(task, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/integrate")
async def integrate(
    body: IntegrateRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Run table discovery plus column matching for a query table."""
    return await _run_task(
        request,
        db,
        task_type="INTEGRATE",
        tenant_id=body.tenant_id,
        query_table_id=body.query_table_id,
        target_table_id=None,
        options=body.options,
    )


@router.post("/discover")
async def discover(
    body: IntegrateRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Run table discovery only for a query table."""
    return await _run_task(
        request,
        db,
        task_type="DISCOVER_ONLY",
        tenant_id=body.tenant_id,
        query_table_id=body.query_table_id,
        target_table_id=None,
        options=body.options,
    )


@router.post("/match")
async def match(
    body: MatchRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Run direct source-target column matching."""
    return await _run_task(
        request,
        db,
        task_type="MATCH_ONLY",
        tenant_id=body.tenant_id,
        query_table_id=body.source_table_id,
        target_table_id=body.target_table_id,
        options=body.options,
    )
