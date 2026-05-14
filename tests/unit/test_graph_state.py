"""Regression tests for graph state schema keys."""

from __future__ import annotations

import pytest
from langgraph.graph import END, START, StateGraph

from adacascade import llm_runtime
from adacascade.agents import matcher, planner
from adacascade.llm_schemas import MatchResult
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


@pytest.mark.anyio
async def test_planner_preserves_explicit_plan_options() -> None:
    """Planner must keep demo/runtime options while adding algorithm defaults."""
    result = await planner.run(
        {
            "task_id": "task-1",
            "tenant_id": "default",
            "task_type": "INTEGRATE",
            "query_table_id": "source-table",
            "target_table_id": None,
            "query_profile": {
                "table_id": "source-table",
                "table_name": "source",
                "columns": [
                    {"name": "id", "dtype": "int", "distinct_ratio": 1.0},
                    {"name": "name", "dtype": "str", "distinct_ratio": 0.5},
                ],
                "sample_rows": [],
            },
            "plan": {
                "llm_cache_enabled": True,
                "matcher_llm_concurrency": 8,
                "matcher_top_k": 3,
            },
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert result["subtask"] == "JOIN"
    assert result["plan"]["theta_1"] == 0.2
    assert result["plan"]["k_2"] == 40
    assert result["plan"]["llm_cache_enabled"] is True
    assert result["plan"]["matcher_llm_concurrency"] == 8
    assert result["plan"]["matcher_top_k"] == 3


@pytest.mark.anyio
async def test_matcher_runtime_metadata_survives_langgraph_state_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matcher metrics must survive graph state filtering for diagnostics."""

    async def fake_verify_pairs_async(
        pairs: list[dict[str, object]], *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        return [
            {
                **pairs[0],
                "llm_result": MatchResult(
                    reasoning="same", score=0.9, is_equivalent=True
                ),
                "cache_hit": False,
                "llm_latency_ms": 12.0,
            }
        ]

    monkeypatch.setattr(llm_runtime, "_active_backend", "api")
    monkeypatch.setattr(
        matcher,
        "filter_cpi",
        lambda *_args, **_kwargs: [
            {
                "src_idx": 0,
                "tgt_idx": 0,
                "src_col_id": "src_a",
                "tgt_col_id": "tgt_a",
                "m_score": 0.9,
            }
        ],
    )
    monkeypatch.setattr(matcher, "truncate_per_source", lambda pairs: pairs)
    monkeypatch.setattr(matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async)

    result = await matcher.run(
        {
            "task_id": "",
            "tenant_id": "default",
            "task_type": "MATCH_ONLY",
            "query_profile": {
                "table_id": "source",
                "columns": [
                    {
                        "col_id": "src_a",
                        "name": "name",
                        "dtype": "str",
                        "description": "",
                        "sample_values": ["alice"],
                    }
                ],
            },
            "target_profile": {
                "table_id": "target",
                "columns": [
                    {
                        "col_id": "tgt_a",
                        "name": "name",
                        "dtype": "str",
                        "description": "",
                        "sample_values": ["alice"],
                    }
                ],
            },
            "plan": {"llm_cache_enabled": True},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert result["stage_timings_ms"]["llm_verification"] >= 0
    assert result["matcher_metrics"]["verified_pair_count"] == 1
    assert result["llm_runtime"]["backend"] == "api"
