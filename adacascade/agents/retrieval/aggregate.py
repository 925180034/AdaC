"""TLCF aggregation — C3-local normalization and final ranking."""

from __future__ import annotations

from typing import Any

import structlog

from adacascade.config import settings

log = structlog.get_logger(__name__)


def min_max_norm(scores: list[float], eps: float = 1e-8) -> list[float]:
    """Normalize scores with min-max scaling inside the current candidate set.

    Args:
        scores: Raw score values for one TLCF layer.
        eps: Small denominator stabilizer from Algorithm Spec §3.5.

    Returns:
        Min-max normalized scores. Empty input returns an empty list.
    """
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    return [(score - lo) / (hi - lo + eps) for score in scores]


def aggregate(
    c3: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate C3 layer scores into final retrieval ranking.

    Args:
        c3: Candidate list with ``table_id``, ``s1``, ``s2``, and ``s3``.
        weights: Optional final score weights keyed by ``w1``, ``w2``, ``w3``.

    Returns:
        Ranking entries sorted by ``score`` descending.
    """
    if not c3:
        return []

    cfg = settings.tlcf_cfg
    active_weights = weights or {
        "w1": float(cfg.get("w1", 0.3)),
        "w2": float(cfg.get("w2", 0.3)),
        "w3": float(cfg.get("w3", 0.4)),
    }

    s1_hat = min_max_norm([float(item.get("s1", 0.0)) for item in c3])
    s2_hat = min_max_norm([float(item.get("s2", 0.0)) for item in c3])
    s3_hat = min_max_norm([float(item.get("s3", 0.0)) for item in c3])

    ranking: list[dict[str, Any]] = []
    for idx, item in enumerate(c3):
        score = (
            active_weights["w1"] * s1_hat[idx]
            + active_weights["w2"] * s2_hat[idx]
            + active_weights["w3"] * s3_hat[idx]
        )
        ranking.append(
            {
                "table_id": item["table_id"],
                "score": score,
                "layer_scores": {
                    "s1": float(item.get("s1", 0.0)),
                    "s2": float(item.get("s2", 0.0)),
                    "s3": float(item.get("s3", 0.0)),
                },
                "normalized": {
                    "s1_hat": s1_hat[idx],
                    "s2_hat": s2_hat[idx],
                    "s3_hat": s3_hat[idx],
                },
            }
        )

    ranking.sort(key=lambda item: item["score"], reverse=True)
    log.info("retrieval.aggregate", c3_size=len(c3), ranking_size=len(ranking))
    return ranking
