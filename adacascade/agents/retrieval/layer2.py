"""TLCF Layer 2 — Qdrant dense vector search + C₂ intersection constraint.

Algorithm Spec §3.3. C₂ = {Tc ∈ C₁ ∩ W | S₂(Tq,Tc) > θ₂}.
Fallback: if |C₂| < 3, relax to top-3 from W ∪ C₁ and set degraded=True.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


def intersect_c2(
    c1: list[dict[str, Any]],
    qdrant_ids: set[str],
    qdrant_scores: dict[str, float],
    theta_2: float,
    fallback: bool = False,
) -> list[dict[str, Any]]:
    """Compute C₂ = C₁ ∩ W filtered by S₂ > θ₂ (formula 3-9).

    Args:
        c1: C₁ results from Layer 1, each dict has {table_id, s1}.
        qdrant_ids: Set of table_ids returned by Qdrant top-k search.
        qdrant_scores: {table_id: cosine_score} from Qdrant.
        theta_2: S₂ threshold.
        fallback: If True, relax constraint when |C₂| < 3.

    Returns:
        List of dicts: {table_id, s1, s2} for each C₂ member.
    """
    c1_ids = {item["table_id"]: item for item in c1}
    c2: list[dict[str, Any]] = []

    for tid in qdrant_ids:
        if tid not in c1_ids:
            continue  # intersection constraint
        s2 = qdrant_scores.get(tid, 0.0)
        if s2 > theta_2:
            c2.append({**c1_ids[tid], "s2": s2})

    if len(c2) < 3 and fallback:
        log.warning("retrieval.l2.fallback", c2_size=len(c2))
        merged = [
            {
                "table_id": tid,
                "s1": entry["s1"],
                "s2": qdrant_scores.get(tid, 0.0),
            }
            for tid, entry in c1_ids.items()
        ]
        merged.sort(key=lambda x: (x["s2"], x["s1"]), reverse=True)
        c2 = merged[:3]

    log.info("retrieval.l2", c2_size=len(c2), theta_2=theta_2)
    return c2


async def search_and_build_c2(
    *,
    c1: list[dict[str, Any]],
    query_vector: list[float],
    tenant_id: str,
    theta_2: float,
    k_2: int,
    source_system: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Run Qdrant search and compute C₂. Returns (c2, degraded).

    Args:
        c1: Output of Layer 1.
        query_vector: Normalized SBERT embedding of query table.
        tenant_id: Tenant filter for Qdrant.
        theta_2: S₂ cosine threshold.
        k_2: Qdrant top-k to retrieve.
        source_system: Optional corpus/source filter for Qdrant.

    Returns:
        Tuple of (C₂ list, degraded flag).
    """
    from adacascade.indexing.registry import get_qdrant

    qdrant = get_qdrant()
    hits = await qdrant.search_tables(
        vector=query_vector,
        tenant_id=tenant_id,
        top_k=k_2,
        source_system=source_system,
    )

    qdrant_ids = {h["table_id"] for h in hits}
    qdrant_scores = {h["table_id"]: h["score"] for h in hits}

    c2_without_fallback = intersect_c2(c1, qdrant_ids, qdrant_scores, theta_2)
    degraded = len(c2_without_fallback) < 3 and len(c1) > 0
    c2 = (
        intersect_c2(c1, qdrant_ids, qdrant_scores, theta_2, fallback=True)
        if degraded
        else c2_without_fallback
    )
    return c2, degraded
