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
