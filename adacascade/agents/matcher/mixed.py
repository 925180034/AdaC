"""Mixed column similarity with scenario-adaptive weights."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from adacascade.agents.matcher.stat_sim import _get, sim_stat
from adacascade.agents.matcher.struct_sim import sim_type
from adacascade.agents.matcher.text_sim import sim_name
from adacascade.config import settings

Scenario = Literal["SMD", "SSD", "SLD"]


class MixedScore(TypedDict):
    """Mixed similarity score and component values."""

    score: float
    sim_name: float
    sim_type: float
    sim_stat: float


def scenario_weights(scenario: Scenario) -> dict[str, float]:
    """Load matcher weights for a scenario.

    Args:
        scenario: Matching scenario name.

    Returns:
        Mapping with text, struct, and stat weights.
    """
    weights = settings.matcher_cfg.get("scenario_weights", {})
    selected = weights.get(scenario, {})
    return {
        "text": float(selected.get("text", 0.0)),
        "struct": float(selected.get("struct", 0.0)),
        "stat": float(selected.get("stat", 0.0)),
    }


def mixed_score(col_a: Any, col_b: Any, scenario: Scenario) -> MixedScore:
    """Compute mixed similarity for one source-target column pair.

    Args:
        col_a: Source column profile.
        col_b: Target column profile.
        scenario: Matching scenario name.

    Returns:
        Component scores plus weighted mixed score.
    """
    name_score = sim_name(str(_get(col_a, "name", "")), str(_get(col_b, "name", "")))
    type_score = sim_type(str(_get(col_a, "dtype", "")), str(_get(col_b, "dtype", "")))
    stat_score = sim_stat(col_a, col_b)
    weights = scenario_weights(scenario)
    score = (
        weights["text"] * name_score
        + weights["struct"] * type_score
        + weights["stat"] * stat_score
    )
    return {
        "score": score,
        "sim_name": name_score,
        "sim_type": type_score,
        "sim_stat": stat_score,
    }
