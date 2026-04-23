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
    assert "B" in ids       # in C1 ∩ W and score > theta_2
    assert "A" not in ids   # not in W
    assert "C" not in ids   # not in W
    assert "D" not in ids   # in W but not in C1


def test_c2_fallback_when_empty() -> None:
    from adacascade.agents.retrieval.layer2 import intersect_c2
    c1 = [{"table_id": "A", "s1": 0.8}]
    # No overlap → should fall back to top-3 of W ∪ C1
    result = intersect_c2(c1, {"B"}, {"B": 0.9}, theta_2=0.55, fallback=True)
    assert len(result) > 0
