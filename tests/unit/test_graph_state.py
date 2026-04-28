"""Regression tests for graph state schema keys."""

from __future__ import annotations

import pytest
from langgraph.graph import END, START, StateGraph

from adacascade.state import IntegrationState


@pytest.mark.anyio
async def test_operation_table_ids_survive_langgraph_state_schema() -> None:
    """Operation table IDs must reach profiling nodes through LangGraph state."""
    seen_state: dict[str, object] = {}

    async def capture_node(state: IntegrationState) -> IntegrationState:
        seen_state.update(state)
        return state

    graph: StateGraph[IntegrationState, IntegrationState, IntegrationState] = (
        StateGraph(IntegrationState)
    )
    graph.add_node("capture", capture_node)
    graph.add_edge(START, "capture")
    graph.add_edge("capture", END)
    compiled = graph.compile()

    await compiled.ainvoke(
        {
            "task_id": "task-1",
            "tenant_id": "default",
            "task_type": "DISCOVER_ONLY",
            "query_table_id": "source-table",
            "target_table_id": None,
            "plan": {},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert seen_state["query_table_id"] == "source-table"
    assert seen_state["target_table_id"] is None
