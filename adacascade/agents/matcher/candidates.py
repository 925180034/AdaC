"""Candidate column-pair filtering for MatcherAgent."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, NotRequired, TypedDict

from adacascade.agents.matcher.mixed import Scenario, mixed_score
from adacascade.agents.matcher.stat_sim import _get
from adacascade.config import settings


class ColPair(TypedDict):
    """Candidate source-target column pair."""

    src_col_id: str
    tgt_col_id: str
    src_idx: int
    tgt_idx: int
    m_score: float
    sim_name: NotRequired[float]
    sim_type: NotRequired[float]
    sim_stat: NotRequired[float]


def filter_cpi(
    source_cols: list[Any],
    target_cols: list[Any],
    scenario: Scenario,
    theta_cand: float | None = None,
) -> list[ColPair]:
    """Build C_pi by filtering mixed similarity scores.

    Args:
        source_cols: Source column profiles.
        target_cols: Target column profiles.
        scenario: Matching scenario name.
        theta_cand: Optional candidate threshold.

    Returns:
        Candidate column pairs meeting the threshold.
    """
    threshold = (
        theta_cand
        if theta_cand is not None
        else float(settings.matcher_cfg.get("theta_cand", 0.35))
    )
    pairs: list[ColPair] = []
    for src_idx, src_col in enumerate(source_cols):
        for tgt_idx, tgt_col in enumerate(target_cols):
            score = mixed_score(src_col, tgt_col, scenario)
            if score["score"] >= threshold:
                pairs.append(
                    {
                        "src_col_id": str(_get(src_col, "col_id", src_idx)),
                        "tgt_col_id": str(_get(tgt_col, "col_id", tgt_idx)),
                        "src_idx": src_idx,
                        "tgt_idx": tgt_idx,
                        "m_score": score["score"],
                        "sim_name": score["sim_name"],
                        "sim_type": score["sim_type"],
                        "sim_stat": score["sim_stat"],
                    }
                )
    return pairs


def truncate_per_source(c_pi: list[ColPair], top_n: int | None = None) -> list[ColPair]:
    """Keep the top-N target candidates per source column.

    Args:
        c_pi: Candidate column pairs.
        top_n: Optional max pairs per source column.

    Returns:
        Truncated candidate pairs sorted within each source group by score descending.
    """
    limit = top_n if top_n is not None else settings.MATCH_LLM_TOPN
    by_source: dict[str, list[ColPair]] = defaultdict(list)
    for pair in c_pi:
        by_source[pair["src_col_id"]].append(pair)

    result: list[ColPair] = []
    for src_col_id in sorted(by_source):
        pairs = sorted(
            by_source[src_col_id], key=lambda pair: pair["m_score"], reverse=True
        )
        result.extend(pairs[:limit])
    return result
