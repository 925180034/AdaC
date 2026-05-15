"""RetrievalAgent — TLCF three-layer cascaded filtering."""

from __future__ import annotations

import heapq
import time
from collections.abc import Iterable
from typing import Any, cast

import structlog

from adacascade.agents.retrieval.aggregate import aggregate
from adacascade.agents.retrieval.layer1 import build_c1, sample_tokens
from adacascade.agents.retrieval.layer2 import search_and_build_c2
from adacascade.agents.retrieval.layer3 import batch_verify
from adacascade.api.events import emit_task_event
from adacascade.config import settings
from adacascade.indexing.registry import get_qdrant
from adacascade.state import IntegrationState
from adacascade.agents.profiling import encode_table_vector

log = structlog.get_logger(__name__)


def _plan_float(plan: dict[str, float | int], key: str, default: float) -> float:
    return float(plan.get(key, default))


def _plan_int(plan: dict[str, float | int], key: str, default: int) -> int:
    return int(plan.get(key, default))


def _enrich(
    entries: list[dict[str, Any]], profiles: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [{**entry, **profiles.get(str(entry["table_id"]), {})} for entry in entries]


def _column_vector(table_name: str, column: dict[str, Any]) -> list[float]:
    return encode_table_vector(
        table_name,
        [
            {
                "col_name": str(column.get("name", "")),
                "col_type": str(column.get("dtype", "str")),
                "col_description": str(column.get("description", "")),
            }
        ],
    )


def _merge_candidates(
    candidates: list[dict[str, Any]], additions: Iterable[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    merged = {str(entry["table_id"]): dict(entry) for entry in candidates}
    for entry in additions:
        table_id = str(entry["table_id"])
        if table_id not in merged or float(entry["s1"]) > float(merged[table_id]["s1"]):
            merged[table_id] = dict(entry)
    results = list(merged.values())
    results.sort(key=lambda entry: float(entry["s1"]), reverse=True)
    return results[:limit]


def _profile_sample_tokens(profile: dict[str, Any]) -> set[str]:
    return sample_tokens([dict(column) for column in profile.get("columns", [])])


def recall_tables_by_samples(
    *,
    query_profile: dict[str, Any],
    candidate_profiles: dict[str, dict[str, Any]],
    min_overlap: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    query_tokens = _profile_sample_tokens(query_profile)
    if not query_tokens:
        return []
    scores: list[tuple[float, str]] = []
    for table_id, profile in candidate_profiles.items():
        candidate_tokens = _profile_sample_tokens(profile)
        overlap = query_tokens & candidate_tokens
        if len(overlap) < min_overlap:
            continue
        union = query_tokens | candidate_tokens
        if not union:
            continue
        score = len(overlap) / len(union)
        if limit is None or len(scores) < limit:
            heapq.heappush(scores, (score, str(table_id)))
        elif score > scores[0][0]:
            heapq.heapreplace(scores, (score, str(table_id)))
    return [
        {"table_id": table_id, "s1": score}
        for score, table_id in sorted(scores, reverse=True)
    ]


async def recall_tables_by_columns(
    *,
    query_profile: dict[str, Any],
    tenant_id: str,
    top_k: int,
    source_system: str | None,
    candidate_profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    qdrant = get_qdrant()
    scores: dict[str, float] = {}
    query_name = str(query_profile.get("table_name", query_profile.get("table_id", "")))
    for column in query_profile.get("columns", []):
        vector = _column_vector(query_name, dict(column))
        hits = await qdrant.search_columns(
            vector=vector,
            tenant_id=tenant_id,
            top_k=top_k,
            source_system=source_system,
        )
        for hit in hits:
            table_id = str(hit["table_id"])
            if table_id in candidate_profiles:
                scores[table_id] = max(scores.get(table_id, 0.0), float(hit["score"]))
    return [
        {"table_id": table_id, "s1": score}
        for table_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


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
    k_1 = _plan_int(plan, "k_1", int(cfg.get("k_1", 120)))
    c1 = build_c1(
        str(query_profile.get("text_blob", "")),
        cast(list[str], query_profile.get("type_multiset", [])),
        candidates,
        _plan_float(plan, "theta_1", float(cfg.get("theta_1", 0.2))),
        k_1,
        tenant_id=tenant_id,
        corpus=corpus,
        query_columns=cast(list[dict[str, Any]], query_profile.get("columns", [])),
        join_sample_boost_enabled=bool(plan.get("join_sample_boost_enabled", False)),
        join_sample_boost_weight=float(plan.get("join_sample_boost_weight", 0.0)),
    )
    source_system = f"retrieval|{corpus}" if corpus != "all" else None
    column_recall = []
    if bool(plan.get("column_recall_enabled", False)):
        column_recall = await recall_tables_by_columns(
            query_profile=query_profile,
            tenant_id=tenant_id,
            top_k=_plan_int(plan, "column_recall_top_k", 20),
            source_system=source_system,
            candidate_profiles=candidate_profiles,
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
                c1=[dict(entry) for entry in c1],
                query_vector=cast(list[float], query_vector),
                tenant_id=tenant_id,
                theta_2=_plan_float(plan, "theta_2", float(cfg.get("theta_2", 0.55))),
                k_2=_plan_int(plan, "k_2", int(cfg.get("k_2", 40))),
                source_system=source_system,
            )
        except Exception as exc:
            bound_log.warning("retrieval.qdrant_degraded", error=str(exc))
            c2 = [{**entry, "s2": entry["s1"]} for entry in c1]
            l2_degraded = True
    else:
        c2 = [{**entry, "s2": entry["s1"]} for entry in c1]
        l2_degraded = True
    if column_recall:
        add_k = _plan_int(plan, "column_recall_add_k", 10)
        c2 = _merge_candidates(c2, column_recall[:add_k], k_1)
    if bool(plan.get("sample_recall_enabled", False)):
        add_k = _plan_int(plan, "sample_recall_add_k", 10)
        sample_recall = recall_tables_by_samples(
            query_profile=query_profile,
            candidate_profiles=candidate_profiles,
            min_overlap=_plan_int(plan, "sample_recall_min_overlap", 1),
            limit=add_k,
        )
        c2 = _merge_candidates(c2, sample_recall, k_1)
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
            batch_size=int(plan.get("llm_batch_size", cfg.get("l3_batch_size", 10))),
            concurrency=int(plan.get("llm_concurrency", settings.llm_cfg.get("concurrency", 4))),
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
