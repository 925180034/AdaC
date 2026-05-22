"""Integration operation endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adacascade.api.events import emit_task_event, has_task_event
from adacascade.api.middleware import get_tenant_id
from adacascade.config import settings
from adacascade.db.models import (
    ColumnMapping,
    DiscoveryResult,
    IntegrationTask,
    TableRegistry,
)
from adacascade.db.session import get_session

router = APIRouter(tags=["operations"])


class IntegrateRequest(BaseModel):
    """Request body for /integrate and /discover."""

    query_table_id: str
    tenant_id: str = settings.DEFAULT_TENANT_ID
    dataset_id: str | None = None
    options: dict[str, Any] = {}
    user_hint: str | None = None


class MatchRequest(BaseModel):
    """Request body for /match."""

    source_table_id: str
    target_table_id: str
    tenant_id: str = settings.DEFAULT_TENANT_ID
    dataset_id: str | None = None
    options: dict[str, Any] = {}


class RunnableGraph(Protocol):
    """Protocol for graph objects that can execute operation state."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run the graph and return the final operation state."""


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
    """Persist successful task completion and result artifacts."""
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
    """Persist failed task completion details."""
    task.status = "FAILED"
    task.finished_at = datetime.now(timezone.utc)
    task.error_message = str(exc)


def _ensure_ready_table(
    db: Session, table_id: str | None, tenant_id: str, dataset_id: str | None
) -> None:
    """Require a READY table owned by the current tenant and Dataset."""
    if table_id is None:
        return
    query = db.query(TableRegistry).filter_by(table_id=table_id, tenant_id=tenant_id)
    if dataset_id is not None:
        query = query.filter_by(dataset_id=dataset_id)
    table = query.first()
    if table is None or table.status != "READY":
        raise HTTPException(status_code=404, detail="Table not found")


def _output_size(task_type: str, state: dict[str, Any]) -> int:
    """Return the final output size for a completed operation."""
    key = "ranking" if task_type == "DISCOVER_ONLY" else "final_mappings"
    value = state.get(key, [])
    return len(value) if isinstance(value, list) else 0


def _operation_options(options: dict[str, Any], user_hint: str | None) -> dict[str, Any]:
    merged = dict(options)
    if user_hint:
        merged["user_hint"] = user_hint
    return merged


async def _emit_missing_stage_summary(
    task_id: str, *, task_type: str, state: dict[str, Any]
) -> None:
    """Backfill coarse stage events when the graph implementation did not emit them."""
    for agent in ["Planner", "Profiling"]:
        if not await has_task_event(task_id, agent=agent, terminal=True):
            await emit_task_event(
                task_id,
                {"type": "agent_completed", "agent": agent, "status": "SUCCESS"},
            )

    if task_type in {"INTEGRATE", "DISCOVER_ONLY"}:
        retrieval_outputs = {
            "L1": len(state.get("c1_meta", []))
            if isinstance(state.get("c1_meta"), list)
            else 0,
            "L2": len(state.get("c2_vec", []))
            if isinstance(state.get("c2_vec"), list)
            else 0,
            "L3": len(state.get("ranking", []))
            if isinstance(state.get("ranking"), list)
            else 0,
        }
        for layer, output_size in retrieval_outputs.items():
            if not await has_task_event(
                task_id, agent="Retrieval", layer=layer, terminal=True
            ):
                await emit_task_event(
                    task_id,
                    {
                        "type": "agent_completed",
                        "agent": "Retrieval",
                        "layer": layer,
                        "status": "SUCCESS",
                        "output_size": output_size,
                    },
                )

    if task_type in {"INTEGRATE", "MATCH_ONLY"}:
        mapping_count = (
            len(state.get("final_mappings", []))
            if isinstance(state.get("final_mappings"), list)
            else 0
        )
        for layer in ["filtering", "LLM", "decision"]:
            if not await has_task_event(
                task_id, agent="Matcher", layer=layer, terminal=True
            ):
                await emit_task_event(
                    task_id,
                    {
                        "type": "agent_completed",
                        "agent": "Matcher",
                        "layer": layer,
                        "status": "SUCCESS",
                        "output_size": mapping_count,
                    },
                )


async def _execute_task_background(
    graph: RunnableGraph,
    *,
    task_id: str,
    task_type: str,
    initial_state: dict[str, Any],
) -> None:
    """Run graph execution in the background and persist terminal task state."""
    try:
        state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": task_id}},
        )
        with get_session() as db:
            task = db.query(IntegrationTask).filter_by(task_id=task_id).one()
            _persist_success(db, task, state)
        await _emit_missing_stage_summary(task_id, task_type=task_type, state=state)
        final_agent = "Retrieval" if task_type == "DISCOVER_ONLY" else "Matcher"
        await emit_task_event(
            task_id,
            {
                "type": "agent_completed",
                "agent": final_agent,
                "status": "SUCCESS",
                "output_size": _output_size(task_type, state),
            },
        )
        await emit_task_event(task_id, {"type": "task_completed", "status": "SUCCESS"})
    except Exception as exc:
        with get_session() as db:
            task = db.query(IntegrationTask).filter_by(task_id=task_id).one()
            _persist_failure(task, exc)
        await emit_task_event(
            task_id,
            {
                "type": "task_completed",
                "status": "FAILED",
                "message": str(exc),
                "error": str(exc),
            },
        )


async def _submit_task(
    request: Request,
    background_tasks: BackgroundTasks,
    *,
    task_type: str,
    tenant_id: str,
    query_table_id: str,
    target_table_id: str | None,
    dataset_id: str | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    """Persist a running task and schedule graph execution."""
    task_options = dict(options)
    if dataset_id is not None:
        task_options["dataset_id"] = dataset_id
    with get_session() as db:
        _ensure_ready_table(db, query_table_id, tenant_id, dataset_id)
        _ensure_ready_table(db, target_table_id, tenant_id, dataset_id)
        task = _create_task(
            db,
            task_type=task_type,
            tenant_id=tenant_id,
            query_table_id=query_table_id,
            target_table_id=target_table_id,
            options=task_options,
        )
        task_id = task.task_id

    initial_state = {
        "task_id": task_id,
        "tenant_id": tenant_id,
        "dataset_id": dataset_id,
        "task_type": task_type,
        "query_table_id": query_table_id,
        "target_table_id": target_table_id,
        "plan": task_options,
        "status": "RUNNING",
        "degraded": False,
    }
    await emit_task_event(
        task_id,
        {"type": "task_created", "status": "RUNNING", "task_type": task_type},
    )
    background_tasks.add_task(
        _execute_task_background,
        request.app.state.graph,
        task_id=task_id,
        task_type=task_type,
        initial_state=initial_state,
    )
    return {"task_id": task_id, "status": "RUNNING", "state": initial_state}


@router.post("/integrate")
async def integrate(
    body: IntegrateRequest, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Schedule table discovery plus column matching for a query table."""
    return await _submit_task(
        request,
        background_tasks,
        task_type="INTEGRATE",
        tenant_id=get_tenant_id(request),
        query_table_id=body.query_table_id,
        target_table_id=None,
        dataset_id=body.dataset_id,
        options=_operation_options(body.options, body.user_hint),
    )


@router.post("/discover")
async def discover(
    body: IntegrateRequest, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Schedule table discovery only for a query table."""
    return await _submit_task(
        request,
        background_tasks,
        task_type="DISCOVER_ONLY",
        tenant_id=get_tenant_id(request),
        query_table_id=body.query_table_id,
        target_table_id=None,
        dataset_id=body.dataset_id,
        options=_operation_options(body.options, body.user_hint),
    )


@router.post("/match")
async def match(
    body: MatchRequest, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """Schedule direct source-target column matching."""
    return await _submit_task(
        request,
        background_tasks,
        task_type="MATCH_ONLY",
        tenant_id=get_tenant_id(request),
        query_table_id=body.source_table_id,
        target_table_id=body.target_table_id,
        dataset_id=body.dataset_id,
        options=body.options,
    )
