"""Statistical distribution similarity functions for MatcherAgent."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from adacascade.config import settings

_NUMERIC_TYPES = {"int", "float", "date"}
_CATEGORICAL_TYPES = {"str", "bool"}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _relative_similarity(a: float, b: float, eps: float) -> float:
    return _clamp01(1.0 - abs(a - b) / (max(abs(a), abs(b)) + eps))


def sim_num(stats_a: Any, stats_b: Any) -> float:
    """Compute numeric-statistics similarity.

    Args:
        stats_a: Numeric stats with mean, std, q25, q50, q75.
        stats_b: Numeric stats with mean, std, q25, q50, q75.

    Returns:
        Weighted numeric similarity in [0, 1].
    """
    if stats_a is None or stats_b is None:
        return 0.0

    cfg = settings.matcher_cfg
    eps = float(cfg.get("epsilon", 1e-8))
    sim_mean = _relative_similarity(
        float(_get(stats_a, "mean", 0.0)), float(_get(stats_b, "mean", 0.0)), eps
    )
    sim_std = _relative_similarity(
        float(_get(stats_a, "std", 0.0)), float(_get(stats_b, "std", 0.0)), eps
    )
    sim_quantile = (
        sum(
            _relative_similarity(
                float(_get(stats_a, key, 0.0)), float(_get(stats_b, key, 0.0)), eps
            )
            for key in ("q25", "q50", "q75")
        )
        / 3.0
    )

    beta_1 = float(cfg.get("beta_1", 0.4))
    beta_2 = float(cfg.get("beta_2", 0.3))
    beta_3 = float(cfg.get("beta_3", 0.3))
    return beta_1 * sim_mean + beta_2 * sim_std + beta_3 * sim_quantile


def sim_dist(freq_a: Mapping[str, float], freq_b: Mapping[str, float]) -> float:
    """Compute cosine similarity between categorical frequency maps.

    Args:
        freq_a: First normalized value-frequency map.
        freq_b: Second normalized value-frequency map.

    Returns:
        Cosine similarity in [0, 1].
    """
    keys = set(freq_a) | set(freq_b)
    if not keys:
        return 0.0
    dot = sum(float(freq_a.get(key, 0.0)) * float(freq_b.get(key, 0.0)) for key in keys)
    norm_a = math.sqrt(sum(float(freq_a.get(key, 0.0)) ** 2 for key in keys))
    norm_b = math.sqrt(sum(float(freq_b.get(key, 0.0)) ** 2 for key in keys))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _top_k_to_freq(stats: Any) -> dict[str, float]:
    top_k = _get(stats, "top_k", []) or []
    return {str(value): float(freq) for value, freq in top_k}


def sim_cat(stats_a: Any, stats_b: Any) -> float:
    """Compute categorical-statistics similarity.

    Args:
        stats_a: Categorical stats with top_k value frequencies.
        stats_b: Categorical stats with top_k value frequencies.

    Returns:
        Weighted categorical similarity in [0, 1].
    """
    if stats_a is None or stats_b is None:
        return 0.0

    freq_a = _top_k_to_freq(stats_a)
    freq_b = _top_k_to_freq(stats_b)
    values_a, values_b = set(freq_a), set(freq_b)
    union = values_a | values_b
    sim_jac_vals = len(values_a & values_b) / len(union) if union else 0.0

    cfg = settings.matcher_cfg
    gamma_1 = float(cfg.get("gamma_1", 0.5))
    gamma_2 = float(cfg.get("gamma_2", 0.5))
    return gamma_1 * sim_jac_vals + gamma_2 * sim_dist(freq_a, freq_b)


def sim_stat(col_a: Any, col_b: Any) -> float:
    """Dispatch statistical similarity by column data type.

    Args:
        col_a: First column profile.
        col_b: Second column profile.

    Returns:
        Numeric or categorical statistical similarity, or 0.0 for incompatible types.
    """
    dtype_a = _get(col_a, "dtype")
    dtype_b = _get(col_b, "dtype")
    if dtype_a in _NUMERIC_TYPES and dtype_b in _NUMERIC_TYPES:
        return sim_num(_get(col_a, "numeric_stats"), _get(col_b, "numeric_stats"))
    if dtype_a in _CATEGORICAL_TYPES and dtype_b in _CATEGORICAL_TYPES:
        return sim_cat(
            _get(col_a, "categorical_stats"), _get(col_b, "categorical_stats")
        )
    return 0.0
