"""RetrievalAgent — TLCF three-layer cascaded filtering."""

from __future__ import annotations

import time
from typing import Any, cast

import structlog

from adacascade.agents.retrieval.aggregate import aggregate
from adacascade.agents.retrieval.layer1 import build_c1
from adacascade.agents.retrieval.layer2 import search_and_build_c2
from adacascade.agents.retrieval.layer3 import batch_verify
from adacascade.api.events import emit_task_event
from adacascade.config import settings
from adacascade.state import IntegrationState

log = structlog.get_logger(__name__)


def _plan_float(plan: dict[str, float | int], key: str, default: float) -> float:
    return float(plan.get(key, default))


def _plan_int(plan: dict[str, float | int], key: str, default: int) -> int:
    return int(plan.get(key, default))


def _enrich(
    entries: list[dict[str, Any]], profiles: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [{**entry, **profiles.get(str(entry["table_id"]), {})} for entry in entries]


async def run(state: IntegrationState) -> IntegrationState:
    """LangGraph node: execute TLCF and write final table ranking."""
    task_id = state.get("task_id", "")
    bound_log = log.bind(task_id=task_id)
    query_profile = cast(dict[str, Any], state.get("query_profile", {}))
    candidate_profiles = cast(
        dict[str, dict[str, Any]], state.get("candidate_profiles", {})
    )
    plan = state.get("plan", {})
    tenant_id = str(state.get("tenant_id", "default"))
    corpus = str(state.get("corpus", "all"))
    cfg = settings.tlcf_cfg

    candidates = list(candidate_profiles.values())
    stage_timings_ms = {"L1": 0.0, "L2": 0.0, "L3": 0.0, "aggregate": 0.0}
    if task_id:
        await emit_task_event(
            task_id,
            {
                "type": "agent_started",
                "agent": "Retrieval",
                "layer": "L1",
                "status": "RUNNING",
                "input_size": len(candidates),
            },
        )
    if not candidates:
        bound_log.info("retrieval.empty_pool")
        if task_id:
            await emit_task_event(
                task_id,
                {
                    "type": "agent_completed",
                    "agent": "Retrieval",
                    "layer": "L1",
                    "status": "SUCCESS",
                    "output_size": 0,
                },
            )
            for layer in ["L2", "L3"]:
                await emit_task_event(
                    task_id,
                    {
                        "type": "agent_started",
                        "agent": "Retrieval",
                        "layer": layer,
                        "status": "RUNNING",
                        "input_size": 0,
                    },
                )
                await emit_task_event(
                    task_id,
                    {
                        "type": "agent_completed",
                        "agent": "Retrieval",
                        "layer": layer,
                        "status": "SUCCESS",
                        "output_size": 0,
                    },
                )
        return {
            **state,
            "c1_meta": [],
            "c2_vec": [],
            "c3_llm": [],
            "ranking": [],
            "degraded": False,
            "stage_timings_ms": stage_timings_ms,
        }

    started = time.perf_counter()
    c1 = build_c1(
        str(query_profile.get("text_blob", "")),
        cast(list[str], query_profile.get("type_multiset", [])),
        candidates,
        _plan_float(plan, "theta_1", float(cfg.get("theta_1", 0.2))),
        _plan_int(plan, "k_1", int(cfg.get("k_1", 120))),
        tenant_id=tenant_id,
        corpus=corpus,
    )
    stage_timings_ms["L1"] = (time.perf_counter() - started) * 1000
    if task_id:
        await emit_task_event(
            task_id,
            {
                "type": "agent_completed",
                "agent": "Retrieval",
                "layer": "L1",
                "status": "SUCCESS",
                "output_size": len(c1),
                "timing_ms": stage_timings_ms["L1"],
            },
        )
        await emit_task_event(
            task_id,
            {
                "type": "agent_started",
                "agent": "Retrieval",
                "layer": "L2",
                "status": "RUNNING",
                "input_size": len(c1),
            },
        )

    l2_degraded = False
    l3_degraded = False
    started = time.perf_counter()
    query_vector = query_profile.get("table_vector")
    if query_vector:
        try:
            c2, l2_degraded = await search_and_build_c2(
                c1=cast(list[dict[str, Any]], c1),
                query_vector=cast(list[float], query_vector),
                tenant_id=tenant_id,
                theta_2=_plan_float(plan, "theta_2", float(cfg.get("theta_2", 0.55))),
                k_2=_plan_int(plan, "k_2", int(cfg.get("k_2", 40))),
            )
        except Exception as exc:
            bound_log.warning("retrieval.qdrant_degraded", error=str(exc))
            c2 = [{**entry, "s2": entry["s1"]} for entry in c1]
            l2_degraded = True
    else:
        c2 = [{**entry, "s2": entry["s1"]} for entry in c1]
        l2_degraded = True
    stage_timings_ms["L2"] = (time.perf_counter() - started) * 1000

    if task_id:
        await emit_task_event(
            task_id,
            {
                "type": "agent_degraded" if l2_degraded else "agent_completed",
                "agent": "Retrieval",
                "layer": "L2",
                "status": "DEGRADED" if l2_degraded else "SUCCESS",
                "output_size": len(c2),
                "timing_ms": stage_timings_ms["L2"],
                "reason": "vector search fallback" if l2_degraded else None,
            },
        )
        await emit_task_event(
            task_id,
            {
                "type": "agent_started",
                "agent": "Retrieval",
                "layer": "L3",
                "status": "RUNNING",
                "input_size": len(c2),
            },
        )

    c2_enriched = _enrich(c2, candidate_profiles)
    started = time.perf_counter()
    try:
        c3 = await batch_verify(
            c2=c2_enriched,
            query_name=str(
                query_profile.get("table_name", query_profile.get("table_id", ""))
            ),
            query_cols=cast(list[dict[str, Any]], query_profile.get("columns", [])),
            task_type=state.get("subtask", "JOIN"),
            theta_3=_plan_float(plan, "theta_3", float(cfg.get("theta_3", 0.5))),
            batch_size=int(cfg.get("l3_batch_size", 10)),
            use_cache=bool(plan.get("llm_cache_enabled", False)),
        )
    except Exception as exc:
        bound_log.warning("retrieval.l3_degraded", error=str(exc))
        c3 = []
        l3_degraded = True
    stage_timings_ms["L3"] = (time.perf_counter() - started) * 1000
    if task_id:
        await emit_task_event(
            task_id,
            {
                "type": "agent_degraded" if l3_degraded else "agent_completed",
                "agent": "Retrieval",
                "layer": "L3",
                "status": "DEGRADED" if l3_degraded else "SUCCESS",
                "output_size": len(c3),
                "timing_ms": stage_timings_ms["L3"],
                "reason": "LLM verification fallback" if l3_degraded else None,
            },
        )

    c3_enriched = _enrich(c3, candidate_profiles)
    started = time.perf_counter()
    weights = {
        "w1": _plan_float(plan, "w_1", 0.3),
        "w2": _plan_float(plan, "w_2", 0.3),
        "w3": _plan_float(plan, "w_3", 0.4),
    }
    ranking = aggregate(c3_enriched, weights=weights)
    stage_timings_ms["aggregate"] = (time.perf_counter() - started) * 1000
    bound_log.info(
        "retrieval.done", c1=len(c1), c2=len(c2), c3=len(c3), ranking=len(ranking)
    )
    return {
        **state,
        "c1_meta": [item["table_id"] for item in c1],
        "c2_vec": [item["table_id"] for item in c2],
        "c3_llm": [item["table_id"] for item in c3],
        "ranking": ranking,
        "degraded": l2_degraded or l3_degraded,
        "stage_timings_ms": stage_timings_ms,
    }
