"""Task status and result endpoints."""

from __future__ import annotations

import json
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from adacascade.api.events import stream_task_events
from adacascade.api.middleware import get_tenant_id
from adacascade.db.models import (
    AgentStep,
    ColumnMapping,
    DiscoveryResult,
    IntegrationTask,
)
from adacascade.db.session import get_session

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session from the module-level singleton."""
    with get_session() as db:
        yield db


def _json_or_none(raw: str | None) -> Any:
    return json.loads(raw) if raw else None


@router.get("/{task_id}")
async def get_task(
    task_id: str, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Return persisted task status, trace, ranking, and mappings."""
    task = db.query(IntegrationTask).filter_by(task_id=task_id).first()
    if task is None or task.tenant_id != get_tenant_id(request):
        raise HTTPException(status_code=404, detail="Task not found")
    steps = (
        db.query(AgentStep).filter_by(task_id=task_id).order_by(AgentStep.step_id).all()
    )
    results = (
        db.query(DiscoveryResult)
        .filter_by(task_id=task_id)
        .order_by(DiscoveryResult.rank)
        .all()
    )
    mappings = db.query(ColumnMapping).filter_by(task_id=task_id).all()
    return {
        "task_id": task.task_id,
        "tenant_id": task.tenant_id,
        "task_type": task.task_type,
        "query_table_id": task.query_table_id,
        "target_table_id": task.target_table_id,
        "status": task.status,
        "submitted_at": task.submitted_at.isoformat(),
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "error_message": task.error_message,
        "plan_config": _json_or_none(task.plan_config),
        "trace": [
            {
                "step_id": step.step_id,
                "agent_name": step.agent_name,
                "layer": step.layer,
                "input_size": step.input_size,
                "output_size": step.output_size,
                "latency_ms": step.latency_ms,
                "llm_tokens": step.llm_tokens,
                "recall_loss": step.recall_loss,
                "started_at": step.started_at.isoformat(),
                "finished_at": step.finished_at.isoformat()
                if step.finished_at
                else None,
            }
            for step in steps
        ],
        "ranking": [
            {
                "rank": result.rank,
                "candidate_table": result.candidate_table,
                "score": result.score,
                "layer_scores": _json_or_none(result.layer_scores),
            }
            for result in results
        ],
        "mappings": [
            {
                "mapping_id": mapping.mapping_id,
                "src_column_id": mapping.src_column_id,
                "tgt_column_id": mapping.tgt_column_id,
                "scenario": mapping.scenario,
                "confidence": mapping.confidence,
                "is_matched": bool(mapping.is_matched),
                "reasoning": mapping.reasoning,
                "created_at": mapping.created_at.isoformat(),
            }
            for mapping in mappings
        ],
    }


@router.get("/{task_id}/events")
async def get_task_events(task_id: str, request: Request) -> StreamingResponse:
    """Stream task progress events for the current tenant as SSE."""
    with get_session() as db:
        task = db.query(IntegrationTask).filter_by(task_id=task_id).first()
        if task is None or task.tenant_id != get_tenant_id(request):
            raise HTTPException(status_code=404, detail="Task not found")
    return StreamingResponse(
        stream_task_events(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
