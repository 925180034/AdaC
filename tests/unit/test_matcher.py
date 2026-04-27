from __future__ import annotations

import numpy as np
import pytest


def _numeric_col(name: str, col_id: str, mean: float = 10.0) -> dict[str, object]:
    return {
        "col_id": col_id,
        "name": name,
        "dtype": "int",
        "numeric_stats": {
            "mean": mean,
            "std": 2.0,
            "q25": mean - 1,
            "q50": mean,
            "q75": mean + 1,
        },
        "categorical_stats": None,
    }


def _cat_col(
    name: str, col_id: str, top_k: list[tuple[str, float]]
) -> dict[str, object]:
    return {
        "col_id": col_id,
        "name": name,
        "dtype": "str",
        "numeric_stats": None,
        "categorical_stats": {"top_k": top_k},
    }


def test_name_sim() -> None:
    from adacascade.agents.matcher.text_sim import sim_name, tokenize

    assert tokenize("user_id") == {"user", "id"}
    assert tokenize("userId") == {"user", "id"}
    assert sim_name("user_id", "userId") >= 0.8


def test_type_compat() -> None:
    from adacascade.agents.matcher.struct_sim import sim_type

    assert sim_type("int", "int") == pytest.approx(1.0)
    assert sim_type("int", "float") == pytest.approx(0.5)
    assert sim_type("int", "str") == pytest.approx(0.5)
    assert sim_type("date", "int") == pytest.approx(0.0)


def test_num_stat() -> None:
    from adacascade.agents.matcher.stat_sim import sim_num

    stats = {"mean": 10.0, "std": 2.0, "q25": 8.0, "q50": 10.0, "q75": 12.0}
    far_stats = {"mean": 100.0, "std": 20.0, "q25": 80.0, "q50": 100.0, "q75": 120.0}

    assert sim_num(stats, stats) == pytest.approx(1.0)
    assert sim_num(stats, far_stats) < 0.2


def test_cat_stat() -> None:
    from adacascade.agents.matcher.stat_sim import sim_cat

    a = {"top_k": [("M", 0.5), ("F", 0.5)]}
    overlap = {"top_k": [("M", 0.6), ("F", 0.4)]}
    disjoint = {"top_k": [("CA", 0.5), ("NY", 0.5)]}

    assert sim_cat(a, overlap) > sim_cat(a, disjoint)
    assert sim_cat(a, overlap) > 0.9


def test_scenario_weights() -> None:
    from adacascade.agents.matcher.mixed import mixed_score, scenario_weights

    src = _numeric_col("alpha", "s1")
    tgt = _numeric_col("omega", "t1")
    smd = mixed_score(src, tgt, "SMD")
    sld = mixed_score(src, tgt, "SLD")
    weights = scenario_weights("SMD")

    assert weights["stat"] == pytest.approx(0.0)
    assert smd["sim_stat"] == pytest.approx(1.0)
    assert smd["score"] == pytest.approx(
        weights["text"] * smd["sim_name"] + weights["struct"] * smd["sim_type"]
    )
    assert sld["score"] > smd["score"]


def test_filter_and_truncate_candidates() -> None:
    from adacascade.agents.matcher.candidates import filter_cpi, truncate_per_source

    source_cols = [_numeric_col("value", "src")]
    target_cols = [
        _numeric_col(f"value_{i}", f"tgt{i}", mean=float(i + 1)) for i in range(12)
    ]

    pairs = filter_cpi(source_cols, target_cols, "SMD", theta_cand=0.0)
    truncated = truncate_per_source(pairs, top_n=10)

    assert len(pairs) == 12
    assert len(truncated) == 10
    assert all(pair["src_col_id"] == "src" for pair in truncated)
    assert truncated == sorted(
        truncated, key=lambda pair: pair["m_score"], reverse=True
    )


def test_decide_and_hungarian_1to1() -> None:
    from adacascade.agents.matcher.decision import decide, hungarian_1to1

    confidence = np.array(
        [
            [0.9, 0.2],
            [0.8, 0.75],
        ]
    )

    assert decide(0.70, theta_match=0.70) is True
    assert decide(0.69, theta_match=0.70) is False
    assert hungarian_1to1(confidence, threshold=0.70) == {0: 0, 1: 1}


def test_sim_stat_dispatch() -> None:
    from adacascade.agents.matcher.stat_sim import sim_stat

    assert sim_stat(_numeric_col("age", "a"), _numeric_col("years", "b")) > 0.9
    assert (
        sim_stat(
            _cat_col("sex", "a", [("M", 0.5), ("F", 0.5)]),
            _cat_col("gender", "b", [("M", 0.6), ("F", 0.4)]),
        )
        > 0.9
    )
    assert (
        sim_stat(_numeric_col("age", "a"), _cat_col("age", "b", [("old", 1.0)])) == 0.0
    )
