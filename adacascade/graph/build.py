"""LangGraph 1.1 graph definition (System Design §4.2)."""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from adacascade.agents import matcher, planner, profiling, retrieval
from adacascade.api.events import emit_task_event
from adacascade.state import IntegrationState


def route_after_planner(state: IntegrationState) -> str:
    """Route to profiling_pair (MATCH_ONLY) or profiling_pool (others)."""
    return (
        "profiling_pair" if state.get("task_type") == "MATCH_ONLY" else "profiling_pool"
    )


def route_after_profiling(state: IntegrationState) -> str:
    """Route to matcher (MATCH_ONLY) or retrieval (others)."""
    return "matcher" if state.get("task_type") == "MATCH_ONLY" else "retrieval"


def route_after_retrieval(state: IntegrationState) -> str:
    """Route to END (DISCOVER_ONLY) or matcher (INTEGRATE)."""
    return END if state.get("task_type") == "DISCOVER_ONLY" else "matcher"


async def _run_planner_with_events(state: IntegrationState) -> IntegrationState:
    """Run Planner and emit lifecycle events around the real node."""
    task_id = state.get("task_id", "")
    if task_id:
        await emit_task_event(
            task_id, {"type": "agent_started", "agent": "Planner", "status": "RUNNING"}
        )
    try:
        output = await planner.run(state)
    except Exception as exc:
        if task_id:
            await emit_task_event(
                task_id,
                {
                    "type": "agent_failed",
                    "agent": "Planner",
                    "status": "FAILED",
                    "message": str(exc),
                    "error": str(exc),
                },
            )
        raise
    if task_id:
        await emit_task_event(
            task_id,
            {"type": "agent_completed", "agent": "Planner", "status": "SUCCESS"},
        )
    return output


async def _run_profiling_pool_with_events(state: IntegrationState) -> dict[str, Any]:
    """Run pool profiling and emit lifecycle events around the real node."""
    task_id = state.get("task_id", "")
    if task_id:
        await emit_task_event(
            task_id,
            {"type": "agent_started", "agent": "Profiling", "status": "RUNNING"},
        )
    try:
        output = await profiling.run_pool(cast(dict[str, Any], state))
    except Exception as exc:
        if task_id:
            await emit_task_event(
                task_id,
                {
                    "type": "agent_failed",
                    "agent": "Profiling",
                    "status": "FAILED",
                    "message": str(exc),
                    "error": str(exc),
                },
            )
        raise
    if task_id:
        await emit_task_event(
            task_id,
            {"type": "agent_completed", "agent": "Profiling", "status": "SUCCESS"},
        )
    return output


async def _run_profiling_pair_with_events(state: IntegrationState) -> dict[str, Any]:
    """Run pair profiling and emit lifecycle events around the real node."""
    task_id = state.get("task_id", "")
    if task_id:
        await emit_task_event(
            task_id,
            {"type": "agent_started", "agent": "Profiling", "status": "RUNNING"},
        )
    try:
        output = await profiling.run_pair(cast(dict[str, Any], state))
    except Exception as exc:
        if task_id:
            await emit_task_event(
                task_id,
                {
                    "type": "agent_failed",
                    "agent": "Profiling",
                    "status": "FAILED",
                    "message": str(exc),
                    "error": str(exc),
                },
            )
        raise
    if task_id:
        await emit_task_event(
            task_id,
            {"type": "agent_completed", "agent": "Profiling", "status": "SUCCESS"},
        )
    return output


def build_graph() -> StateGraph[IntegrationState, IntegrationState, IntegrationState]:
    """Construct and return the compiled-ready StateGraph."""
    g: StateGraph[IntegrationState, IntegrationState, IntegrationState] = StateGraph(
        IntegrationState
    )

    g.add_node("planner", _run_planner_with_events)
    g.add_node("profiling_pool", _run_profiling_pool_with_events)
    g.add_node("profiling_pair", _run_profiling_pair_with_events)
    g.add_node("retrieval", retrieval.run)
    g.add_node("matcher", matcher.run)

    g.add_edge(START, "planner")
    g.add_conditional_edges(
        "planner",
        route_after_planner,
        {"profiling_pool": "profiling_pool", "profiling_pair": "profiling_pair"},
    )
    g.add_conditional_edges(
        "profiling_pool",
        route_after_profiling,
        {"retrieval": "retrieval", "matcher": "matcher"},
    )
    g.add_edge("profiling_pair", "matcher")
    g.add_conditional_edges(
        "retrieval",
        route_after_retrieval,
        {"matcher": "matcher", END: END},
    )
    g.add_edge("matcher", END)

    return g
