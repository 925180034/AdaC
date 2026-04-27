# tests/unit/test_retrieval.py
import pytest


def test_type_jaccard_basic() -> None:
    from adacascade.agents.retrieval.layer1 import type_jaccard

    # Counter({int:2, str:1}) ∩ Counter({int:1, str:2}) = {int:1, str:1} → inter=2
    # Counter({int:2, str:1}) ∪ Counter({int:2, str:2}) → union=4
    result = type_jaccard(["int", "int", "str"], ["int", "str", "str"])
    assert result == pytest.approx(0.5)


def test_type_jaccard_identical() -> None:
    from adacascade.agents.retrieval.layer1 import type_jaccard

    assert type_jaccard(["int", "str"], ["int", "str"]) == pytest.approx(1.0)


def test_type_jaccard_empty() -> None:
    from adacascade.agents.retrieval.layer1 import type_jaccard

    assert type_jaccard([], []) == pytest.approx(0.0)


def test_compute_s1_range() -> None:
    from adacascade.agents.retrieval.layer1 import compute_s1
    from adacascade.config import settings

    cfg = settings.tlcf_cfg
    w1 = float(cfg.get("omega_1", 0.7))
    w2 = float(cfg.get("omega_2", 0.3))
    expected = w1 * 0.8 + w2 * 0.5
    assert compute_s1(tfidf_sim=0.8, jaccard_sim=0.5) == pytest.approx(expected)


def test_c2_intersection_keeps_only_overlap() -> None:
    """C2 must be C1 ∩ Qdrant_topK, not just Qdrant result."""
    from adacascade.agents.retrieval.layer2 import intersect_c2

    c1 = [
        {"table_id": "A", "s1": 0.8},
        {"table_id": "B", "s1": 0.6},
        {"table_id": "C", "s1": 0.5},
    ]
    qdrant_ids = {"B", "D"}  # D is NOT in C1
    scores = {"B": 0.7, "D": 0.9}
    result = intersect_c2(c1, qdrant_ids, scores, theta_2=0.55)
    ids = [r["table_id"] for r in result]
    assert "B" in ids  # in C1 ∩ W and score > theta_2
    assert "A" not in ids  # not in W
    assert "C" not in ids  # not in W
    assert "D" not in ids  # in W but not in C1


def test_c2_fallback_when_empty() -> None:
    from adacascade.agents.retrieval.layer2 import intersect_c2

    c1 = [{"table_id": "A", "s1": 0.8}]
    # No overlap → should fall back to top-3 of W ∪ C1
    result = intersect_c2(c1, {"B"}, {"B": 0.9}, theta_2=0.55, fallback=True)
    assert len(result) > 0


def test_l3_batch_invalid_schema_raises() -> None:
    """Mock LLM returning invalid JSON must raise via Pydantic, not silently pass."""
    from adacascade.llm_schemas import L3BatchResult
    import pytest

    bad_json = '{"scores": [{"candidate_idx": 1, "score": 1.5, "reason": "x"}]}'
    with pytest.raises(Exception):  # score > 1.0 violates Field(le=1.0)
        L3BatchResult.model_validate_json(bad_json)


def test_l3_batch_missing_idx_scores_zero() -> None:
    """Candidates with no LLM score entry get S3=0.0 and are excluded from C3."""
    from adacascade.agents.retrieval.layer3 import _merge_scores

    c2 = [{"table_id": "A"}, {"table_id": "B"}]
    llm_scores = {1: 0.8}  # only idx=1 (A) scored
    result = _merge_scores(c2, llm_scores, theta_3=0.5)
    assert len(result) == 1
    assert result[0]["table_id"] == "A"
    assert result[0]["s3"] == pytest.approx(0.8)


def test_minmax_edge() -> None:
    from adacascade.agents.retrieval.aggregate import min_max_norm

    assert min_max_norm([0.5, 0.5, 0.5]) == pytest.approx([0.0, 0.0, 0.0])
    assert min_max_norm([]) == []


def test_aggregate_ranking_descending() -> None:
    from adacascade.agents.retrieval.aggregate import aggregate

    c3 = [
        {"table_id": "A", "s1": 0.9, "s2": 0.1, "s3": 0.1},
        {"table_id": "B", "s1": 0.5, "s2": 0.9, "s3": 0.9},
        {"table_id": "C", "s1": 0.1, "s2": 0.5, "s3": 0.5},
    ]
    ranking = aggregate(c3, weights={"w1": 0.2, "w2": 0.4, "w3": 0.4})

    assert [item["table_id"] for item in ranking] == ["B", "C", "A"]
    assert ranking[0]["score"] >= ranking[1]["score"] >= ranking[2]["score"]
    assert ranking[0]["layer_scores"] == {"s1": 0.5, "s2": 0.9, "s3": 0.9}
    assert set(ranking[0]["normalized"]) == {"s1_hat", "s2_hat", "s3_hat"}
