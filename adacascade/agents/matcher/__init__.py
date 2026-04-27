"""MatcherAgent — adaptive schema matching."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import structlog

from adacascade.agents.matcher import llm_verify
from adacascade.agents.matcher.candidates import filter_cpi, truncate_per_source
from adacascade.agents.matcher.decision import decide, hungarian_1to1
from adacascade.agents.matcher.mixed import Scenario
from adacascade.artifacts import save_pkl
from adacascade.config import settings
from adacascade.state import IntegrationState

log = structlog.get_logger(__name__)


def detect_scenario(
    profile: dict[str, Any], scenario_hint: str | None = None
) -> Scenario:
    """Detect the matcher scenario from an explicit hint or profile richness."""
    if scenario_hint in {"SMD", "SSD", "SLD"}:
        return cast(Scenario, scenario_hint)
    columns = profile.get("columns", [])
    has_samples = any(col.get("sample_values") for col in columns)
    has_stats = any(
        col.get("numeric_stats") or col.get("categorical_stats") for col in columns
    )
    if has_stats:
        return "SLD"
    if has_samples:
        return "SSD"
    return "SMD"


def _targets(state: IntegrationState) -> list[dict[str, Any]]:
    task_type = state.get("task_type", "INTEGRATE")
    if task_type == "MATCH_ONLY":
        target = state.get("target_profile")
        return [target] if target else []
    candidate_profiles = cast(
        dict[str, dict[str, Any]], state.get("candidate_profiles", {})
    )
    ranking = cast(list[dict[str, Any]], state.get("ranking", []))
    if ranking:
        return [
            candidate_profiles[str(item["table_id"])]
            for item in ranking
            if str(item.get("table_id")) in candidate_profiles
        ]
    return list(candidate_profiles.values())


def _mapping_entry(
    source_cols: list[dict[str, Any]],
    target_cols: list[dict[str, Any]],
    target_profile: dict[str, Any],
    verified: dict[str, Any],
    scenario: Scenario,
) -> dict[str, Any]:
    src_col = source_cols[int(verified["src_idx"])]
    tgt_col = target_cols[int(verified["tgt_idx"])]
    result = verified["llm_result"]
    return {
        "source_table_id": src_col.get("table_id"),
        "target_table_id": target_profile["table_id"],
        "source_col_id": verified["src_col_id"],
        "target_col_id": verified["tgt_col_id"],
        "source_column": src_col.get("name", ""),
        "target_column": tgt_col.get("name", ""),
        "confidence": result.score,
        "scenario": scenario,
        "reasoning": result.reasoning,
    }


def _apply_one_to_one(
    verified: list[dict[str, Any]], source_size: int, target_size: int
) -> set[tuple[int, int]]:
    matrix = np.zeros((source_size, target_size), dtype=np.float64)
    for item in verified:
        result = item["llm_result"]
        matrix[int(item["src_idx"]), int(item["tgt_idx"])] = float(result.score)
    assignments = hungarian_1to1(matrix)
    return {(src_idx, tgt_idx) for src_idx, tgt_idx in assignments.items()}


async def run(state: IntegrationState) -> IntegrationState:
    """LangGraph node: compute final column mappings."""
    task_id = state.get("task_id", "")
    bound_log = log.bind(task_id=task_id)
    source_profile = cast(dict[str, Any], state.get("query_profile", {}))
    source_cols = cast(list[dict[str, Any]], source_profile.get("columns", []))
    scenario = detect_scenario(source_profile, str(state.get("scenario", "")))
    all_pairs: list[dict[str, Any]] = []
    final_mappings: list[dict[str, Any]] = []

    for src_col in source_cols:
        src_col["table_id"] = source_profile.get("table_id")

    for target_profile in _targets(state):
        target_cols = cast(list[dict[str, Any]], target_profile.get("columns", []))
        if not source_cols or not target_cols:
            continue
        c_pi = filter_cpi(source_cols, target_cols, scenario)
        truncated = truncate_per_source(c_pi)
        all_pairs.extend(cast(list[dict[str, Any]], truncated))
        verified = llm_verify.verify_pairs(
            cast(list[dict[str, Any]], truncated), source_cols, target_cols, scenario
        )
        accepted = [
            item
            for item in verified
            if item["llm_result"].is_equivalent and decide(item["llm_result"].score)
        ]
        if (
            state.get("subtask", "JOIN") == "JOIN"
            and bool(settings.matcher_cfg.get("enable_1to1", True))
            and accepted
        ):
            allowed = _apply_one_to_one(accepted, len(source_cols), len(target_cols))
            accepted = [
                item
                for item in accepted
                if (int(item["src_idx"]), int(item["tgt_idx"])) in allowed
            ]
        final_mappings.extend(
            _mapping_entry(source_cols, target_cols, target_profile, item, scenario)
            for item in accepted
        )

    sim_path = save_pkl(task_id, "sim", all_pairs) if task_id else None
    bound_log.info("matcher.done", pairs=len(all_pairs), mappings=len(final_mappings))
    return {
        **state,
        "similarity_matrix_path": sim_path,
        "final_mappings": final_mappings,
    }
