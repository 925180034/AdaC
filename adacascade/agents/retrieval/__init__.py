"""RetrievalAgent — TLCF three-layer cascaded filtering."""

from __future__ import annotations

from typing import Any, cast

import structlog

from adacascade.agents.retrieval.aggregate import aggregate
from adacascade.agents.retrieval.layer1 import build_c1
from adacascade.agents.retrieval.layer2 import search_and_build_c2
from adacascade.agents.retrieval.layer3 import batch_verify
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
    cfg = settings.tlcf_cfg

    candidates = list(candidate_profiles.values())
    if not candidates:
        bound_log.info("retrieval.empty_pool")
        return {
            **state,
            "c1_meta": [],
            "c2_vec": [],
            "c3_llm": [],
            "ranking": [],
            "degraded": False,
        }

    c1 = build_c1(
        str(query_profile.get("text_blob", "")),
        cast(list[str], query_profile.get("type_multiset", [])),
        candidates,
        _plan_float(plan, "theta_1", float(cfg.get("theta_1", 0.2))),
        _plan_int(plan, "k_1", int(cfg.get("k_1", 120))),
    )

    query_vector = query_profile.get("table_vector")
    if query_vector:
        c2, degraded = await search_and_build_c2(
            c1=cast(list[dict[str, Any]], c1),
            query_vector=cast(list[float], query_vector),
            tenant_id=str(state.get("tenant_id", "default")),
            theta_2=_plan_float(plan, "theta_2", float(cfg.get("theta_2", 0.55))),
            k_2=_plan_int(plan, "k_2", int(cfg.get("k_2", 40))),
        )
    else:
        c2 = [{**entry, "s2": entry["s1"]} for entry in c1]
        degraded = True

    c2_enriched = _enrich(c2, candidate_profiles)
    c3 = await batch_verify(
        c2=c2_enriched,
        query_name=str(
            query_profile.get("table_name", query_profile.get("table_id", ""))
        ),
        query_cols=cast(list[dict[str, Any]], query_profile.get("columns", [])),
        task_type=state.get("subtask", "JOIN"),
        theta_3=_plan_float(plan, "theta_3", float(cfg.get("theta_3", 0.5))),
        batch_size=int(cfg.get("l3_batch_size", 10)),
    )
    c3_enriched = _enrich(c3, candidate_profiles)
    weights = {
        "w1": _plan_float(plan, "w_1", 0.3),
        "w2": _plan_float(plan, "w_2", 0.3),
        "w3": _plan_float(plan, "w_3", 0.4),
    }
    ranking = aggregate(c3_enriched, weights=weights)
    bound_log.info(
        "retrieval.done", c1=len(c1), c2=len(c2), c3=len(c3), ranking=len(ranking)
    )
    return {
        **state,
        "c1_meta": [item["table_id"] for item in c1],
        "c2_vec": [item["table_id"] for item in c2],
        "c3_llm": [item["table_id"] for item in c3],
        "ranking": ranking,
        "degraded": degraded,
    }
