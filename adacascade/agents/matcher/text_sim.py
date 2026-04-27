"""Column-name similarity functions for MatcherAgent."""

from __future__ import annotations

import re

import Levenshtein

from adacascade.config import settings


def _normalize(value: str) -> str:
    return value.strip().lower()


def tokenize(name: str) -> set[str]:
    """Split snake, kebab, space, and camel-case column names into tokens.

    Args:
        name: Column name to tokenize.

    Returns:
        Non-empty lowercase tokens.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    tokens = re.split(r"[_\s\-]+", spaced.lower())
    return {token for token in tokens if token}


def sim_lev(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Similarity in [0, 1].
    """
    a, b = _normalize(s1), _normalize(s2)
    distance = Levenshtein.distance(a, b)
    return 1.0 - distance / max(len(a), len(b), 1)


def sim_seq(s1: str, s2: str) -> float:
    """Compute longest-common-subsequence similarity.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        LCS similarity in [0, 1].
    """
    a, b = _normalize(s1), _normalize(s2)
    if not (a or b):
        return 0.0

    prev = [0] * (len(b) + 1)
    for char_a in a:
        curr = [0]
        for j, char_b in enumerate(b, start=1):
            if char_a == char_b:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(prev[j], curr[-1]))
        prev = curr

    return 2.0 * prev[-1] / (len(a) + len(b))


def sim_jac_name(s1: str, s2: str) -> float:
    """Compute token Jaccard similarity for column names.

    Args:
        s1: First column name.
        s2: Second column name.

    Returns:
        Token-set Jaccard similarity.
    """
    tokens_a, tokens_b = tokenize(s1), tokenize(s2)
    union = tokens_a | tokens_b
    return len(tokens_a & tokens_b) / len(union) if union else 0.0


def sim_name(s1: str, s2: str) -> float:
    """Compute weighted name similarity from edit, sequence, and token scores.

    Args:
        s1: First column name.
        s2: Second column name.

    Returns:
        Weighted similarity in [0, 1].
    """
    cfg = settings.matcher_cfg
    alpha_1 = float(cfg.get("alpha_1", 0.4))
    alpha_2 = float(cfg.get("alpha_2", 0.3))
    alpha_3 = float(cfg.get("alpha_3", 0.3))
    return (
        alpha_1 * sim_lev(s1, s2)
        + alpha_2 * sim_seq(s1, s2)
        + alpha_3 * sim_jac_name(s1, s2)
    )
