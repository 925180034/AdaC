"""TLCF Layer 1 — TF-IDF cosine + type-Jaccard metadata filtering.

Algorithm Spec §3.2. Produces C₁ = TopK({Tc | S1 > θ1}, k1).
"""
from __future__ import annotations

import heapq
import pickle
from collections import Counter
from pathlib import Path
from typing import Any, TypedDict

import structlog
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from adacascade.config import settings

log = structlog.get_logger(__name__)

_TFIDF_PATH = Path(settings.ARTIFACTS_DIR) / "tfidf.pkl"
_vectorizer: Any = None


class C1Entry(TypedDict):
    """One entry in the C₁ candidate set."""

    table_id: str
    s1: float


def _load_tfidf() -> Any:
    """Load the TF-IDF vectorizer from disk (cached after first load).

    Returns:
        A fitted sklearn TfidfVectorizer.

    Raises:
        FileNotFoundError: If the vectorizer pickle does not exist.
    """
    global _vectorizer
    if _vectorizer is not None:
        return _vectorizer
    if not _TFIDF_PATH.exists():
        raise FileNotFoundError(
            f"TF-IDF vectorizer not found at {_TFIDF_PATH}. "
            "Run: python scripts/rebuild_tfidf.py"
        )
    with _TFIDF_PATH.open("rb") as f:
        _vectorizer = pickle.load(f)  # noqa: S301
    return _vectorizer


def compute_s1(tfidf_sim: float, jaccard_sim: float) -> float:
    """S1 = ω1·Sim_TFIDF + ω2·Sim_Jaccard (Algorithm Spec §3.2, formula 3-3).

    Args:
        tfidf_sim: TF-IDF cosine similarity between query and candidate blobs.
        jaccard_sim: Type-multiset Jaccard similarity.

    Returns:
        Combined layer-1 score in [0, 1].
    """
    cfg = settings.tlcf_cfg
    w1: float = float(cfg.get("omega_1", 0.7))
    w2: float = float(cfg.get("omega_2", 0.3))
    return w1 * tfidf_sim + w2 * jaccard_sim


def type_jaccard(types_q: list[str], types_c: list[str]) -> float:
    """Multiset Jaccard on column type lists (Algorithm Spec §3.2, formula 3-5).

    Args:
        types_q: Column type list for the query table (e.g. ["int", "str", "str"]).
        types_c: Column type list for the candidate table.

    Returns:
        Multiset Jaccard similarity in [0, 1]; 0.0 when both lists are empty.
    """
    cq, cc = Counter(types_q), Counter(types_c)
    inter = sum((cq & cc).values())
    union = sum((cq | cc).values())
    return inter / union if union else 0.0


def tfidf_cosine(blob_q: str, blob_c: str) -> float:
    """Cosine similarity between two text blobs via TF-IDF (formula 3-4).

    Args:
        blob_q: Text blob of the query table.
        blob_c: Text blob of the candidate table.

    Returns:
        Cosine similarity in [0, 1].
    """
    vec = _load_tfidf()
    vq = vec.transform([blob_q])
    vc = vec.transform([blob_c])
    sim: float = float(cosine_similarity(vq, vc)[0, 0])
    return sim


def build_c1(
    query_blob: str,
    query_types: list[str],
    candidates: list[dict[str, Any]],
    theta_1: float,
    k_1: int,
) -> list[C1Entry]:
    """Build C₁ = TopK({Tc | S1 > θ1}, k1) using a min-heap (formula 3-6).

    Args:
        query_blob: Text blob of the query table.
        query_types: Column type multiset of the query table.
        candidates: List of dicts with keys: table_id, text_blob, type_multiset.
        theta_1: S1 threshold; candidates with S1 ≤ theta_1 are discarded.
        k_1: Max candidates to keep.

    Returns:
        List of C1Entry dicts ``{table_id, s1}`` sorted by s1 descending.
    """
    vec = _load_tfidf()
    vq = vec.transform([query_blob])

    heap: list[tuple[float, str]] = []  # (s1, table_id) min-heap

    for cand in candidates:
        vc = vec.transform([cand["text_blob"]])
        sim_tf: float = float(cosine_similarity(vq, vc)[0, 0])
        sim_jac: float = type_jaccard(query_types, cand["type_multiset"])
        s1 = compute_s1(sim_tf, sim_jac)

        if s1 <= theta_1:
            continue

        if len(heap) < k_1:
            heapq.heappush(heap, (s1, cand["table_id"]))
        elif s1 > heap[0][0]:
            heapq.heapreplace(heap, (s1, cand["table_id"]))

    results: list[C1Entry] = [
        C1Entry(table_id=tid, s1=score) for score, tid in heap
    ]
    results.sort(key=lambda x: x["s1"], reverse=True)
    log.info("retrieval.l1", c1_size=len(results), theta_1=theta_1, k_1=k_1)
    return results
