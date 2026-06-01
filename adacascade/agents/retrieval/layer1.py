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
_vectorizers: dict[str, tuple[int, int, int, Any]] = {}


class C1Entry(TypedDict):
    """One entry in the C₁ candidate set."""

    table_id: str
    s1: float


def _tfidf_path(
    *,
    tenant_id: str | None = None,
    corpus: str = "all",
    artifacts_dir: Path | None = None,
) -> Path:
    root = artifacts_dir or Path(settings.ARTIFACTS_DIR)
    if corpus == "all" or tenant_id is None:
        return root / "tfidf.pkl"
    return root / f"tfidf_{tenant_id}_{corpus}.pkl"


def clear_cache(path: str | Path | None = None) -> None:
    """Clear cached TF-IDF vectorizers."""
    if path is None:
        _vectorizers.clear()
        return
    _vectorizers.pop(str(Path(path)), None)


def load_tfidf(
    *,
    tenant_id: str | None = None,
    corpus: str = "all",
    artifacts_dir: Path | None = None,
) -> Any:
    """Load a fitted TF-IDF vectorizer, optionally scoped by tenant and corpus."""
    path = _tfidf_path(tenant_id=tenant_id, corpus=corpus, artifacts_dir=artifacts_dir)
    cache_key = str(path)
    if not path.exists():
        raise FileNotFoundError(
            f"TF-IDF vectorizer not found at {path}. "
            "Run: python scripts/rebuild_tfidf.py"
        )
    stat = path.stat()
    fingerprint = hash(path.read_bytes())
    cached = _vectorizers.get(cache_key)
    if cached is not None:
        mtime_ns, size, cached_fingerprint, vectorizer = cached
        if (
            mtime_ns == stat.st_mtime_ns
            and size == stat.st_size
            and cached_fingerprint == fingerprint
        ):
            return vectorizer
    with path.open("rb") as f:
        vectorizer = pickle.load(f)  # noqa: S301
    _vectorizers[cache_key] = (stat.st_mtime_ns, stat.st_size, fingerprint, vectorizer)
    return vectorizer


def _load_tfidf() -> Any:
    return load_tfidf()


_LOW_INFORMATION_SAMPLE_TOKENS = {
    "",
    "0",
    "0.0",
    "0.00",
    "0.000",
    ".0",
    ".00",
    ".000",
    "none",
    "null",
    "nan",
    "n/a",
    "na",
}


def sample_tokens(columns: list[dict[str, Any]]) -> set[str]:
    """Normalize informative column sample values for overlap scoring."""
    tokens: set[str] = set()
    for column in columns:
        for value in column.get("sample_values", []):
            token = str(value).strip().casefold()
            if token not in _LOW_INFORMATION_SAMPLE_TOKENS:
                tokens.add(token)
    return tokens


def _sample_overlap_tokens(
    query_tokens: set[str], candidate_columns: list[dict[str, Any]]
) -> float:
    candidate_tokens = sample_tokens(candidate_columns)
    union = query_tokens | candidate_tokens
    if not union:
        return 0.0
    return len(query_tokens & candidate_tokens) / len(union)


def sample_overlap(
    query_columns: list[dict[str, Any]], candidate_columns: list[dict[str, Any]]
) -> float:
    """Jaccard overlap over normalized column sample values."""
    return _sample_overlap_tokens(sample_tokens(query_columns), candidate_columns)


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


def tfidf_cosine(
    blob_q: str,
    blob_c: str,
    *,
    tenant_id: str | None = None,
    corpus: str = "all",
) -> float:
    """Cosine similarity between two text blobs via TF-IDF (formula 3-4).

    Args:
        blob_q: Text blob of the query table.
        blob_c: Text blob of the candidate table.

    Returns:
        Cosine similarity in [0, 1].
    """
    vec = load_tfidf(tenant_id=tenant_id, corpus=corpus)
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
    *,
    tenant_id: str | None = None,
    corpus: str = "all",
    query_columns: list[dict[str, Any]] | None = None,
    join_sample_boost_enabled: bool = False,
    join_sample_boost_weight: float = 0.0,
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
    vec = load_tfidf(tenant_id=tenant_id, corpus=corpus)
    vq = vec.transform([query_blob])

    heap: list[tuple[float, str]] = []  # (s1, table_id) min-heap
    query_sample_tokens = sample_tokens(query_columns or [])

    for cand in candidates:
        vc = vec.transform([cand["text_blob"]])
        sim_tf: float = float(cosine_similarity(vq, vc)[0, 0])
        sim_jac: float = type_jaccard(query_types, cand["type_multiset"])
        s1 = compute_s1(sim_tf, sim_jac)
        if join_sample_boost_enabled:
            s1 = min(
                1.0,
                s1
                + join_sample_boost_weight
                * _sample_overlap_tokens(query_sample_tokens, list(cand.get("columns", []))),
            )

        if s1 <= theta_1:
            continue

        if len(heap) < k_1:
            heapq.heappush(heap, (s1, cand["table_id"]))
        elif s1 > heap[0][0]:
            heapq.heapreplace(heap, (s1, cand["table_id"]))

    results: list[C1Entry] = [C1Entry(table_id=tid, s1=score) for score, tid in heap]
    results.sort(key=lambda x: x["s1"], reverse=True)
    log.info("retrieval.l1", c1_size=len(results), theta_1=theta_1, k_1=k_1)
    return results
