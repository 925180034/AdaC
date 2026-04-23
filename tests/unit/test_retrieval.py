# tests/unit/test_retrieval.py
from collections import Counter
import pytest


def test_type_jaccard_basic():
    from adacascade.agents.retrieval.layer1 import type_jaccard
    # Counter({int:2, str:1}) ∩ Counter({int:1, str:2}) = {int:1, str:1} → inter=2
    # Counter({int:2, str:1}) ∪ Counter({int:2, str:2}) → union=4
    result = type_jaccard(["int", "int", "str"], ["int", "str", "str"])
    assert result == pytest.approx(0.5)


def test_type_jaccard_identical():
    from adacascade.agents.retrieval.layer1 import type_jaccard
    assert type_jaccard(["int", "str"], ["int", "str"]) == pytest.approx(1.0)


def test_type_jaccard_empty():
    from adacascade.agents.retrieval.layer1 import type_jaccard
    assert type_jaccard([], []) == pytest.approx(0.0)


def test_compute_s1_range():
    from adacascade.agents.retrieval.layer1 import compute_s1
    # with tfidf=0.8 and jaccard=0.5 → 0.7*0.8 + 0.3*0.5 = 0.71
    score = compute_s1(tfidf_sim=0.8, jaccard_sim=0.5)
    assert score == pytest.approx(0.71)
