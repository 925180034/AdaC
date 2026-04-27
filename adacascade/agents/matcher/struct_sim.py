"""Column type compatibility similarity for MatcherAgent."""

from __future__ import annotations

from adacascade.config import settings

COMPATIBLE: set[tuple[str, str]] = {
    ("int", "float"),
    ("float", "int"),
    ("int", "str"),
    ("float", "str"),
    ("date", "str"),
    ("str", "date"),
}


def sim_type(t1: str, t2: str) -> float:
    """Compute structural type compatibility.

    Args:
        t1: First normalized column type.
        t2: Second normalized column type.

    Returns:
        1.0 for exact match, configured partial score for compatible pairs, else 0.0.
    """
    if t1 == t2:
        return 1.0
    if (t1, t2) in COMPATIBLE:
        return float(settings.matcher_cfg.get("delta_type_compat", 0.5))
    return 0.0
