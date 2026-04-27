"""Matcher decision helpers."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

from adacascade.config import settings


def decide(score: float, theta_match: float | None = None) -> bool:
    """Apply the final matcher threshold.

    Args:
        score: LLM or confidence score.
        theta_match: Optional decision threshold.

    Returns:
        True when score is greater than or equal to the threshold.
    """
    threshold = (
        theta_match if theta_match is not None else settings.MATCH_DECISION_THRESHOLD
    )
    return score >= threshold


def hungarian_1to1(
    confidence: NDArray[np.float64], threshold: float | None = None
) -> dict[int, int]:
    """Compute maximum-confidence one-to-one assignments.

    Args:
        confidence: Matrix of source-by-target confidence scores.
        threshold: Optional minimum confidence for accepted assignments.

    Returns:
        Mapping from source row index to target column index.
    """
    active_threshold = (
        threshold if threshold is not None else settings.MATCH_DECISION_THRESHOLD
    )
    if confidence.size == 0:
        return {}

    row_ind, col_ind = linear_sum_assignment(-confidence)
    return {
        int(row): int(col)
        for row, col in zip(row_ind, col_ind)
        if confidence[row, col] >= active_threshold
    }
