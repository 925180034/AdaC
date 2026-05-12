from __future__ import annotations

import json

import pytest


def test_normalized_weights_sum_to_one() -> None:
    from scripts.optimize_retrieval_params import _normalize_weights

    weights = _normalize_weights(2.0, 3.0, 5.0)

    assert weights == {"w_1": 0.2, "w_2": 0.3, "w_3": 0.5}
    assert sum(weights.values()) == pytest.approx(1.0)


def test_objective_score_penalizes_latency() -> None:
    from scripts.optimize_retrieval_params import _objective_score

    fast = _objective_score(recall_at_10=0.7, avg_ms=1_000.0, latency_penalty_ms=10_000.0)
    slow = _objective_score(recall_at_10=0.7, avg_ms=20_000.0, latency_penalty_ms=10_000.0)

    assert fast > slow
    assert fast == pytest.approx(0.6)


def test_trial_params_include_search_space_and_normalized_weights() -> None:
    from scripts.optimize_retrieval_params import _suggest_params

    class FakeTrial:
        def suggest_float(self, name, low, high):
            values = {
                "theta_1": 0.1,
                "theta_2": 0.4,
                "theta_3": 0.3,
                "raw_w1": 0.2,
                "raw_w2": 0.3,
                "raw_w3": 0.5,
            }
            assert low <= values[name] <= high
            return values[name]

        def suggest_categorical(self, name, choices):
            values = {"k_1": 300, "k_2": 120}
            assert values[name] in choices
            return values[name]

    params = _suggest_params(FakeTrial(), k2_choices=[40, 80, 120])

    assert params == {
        "theta_1": 0.1,
        "theta_2": 0.4,
        "theta_3": 0.3,
        "k_1": 300,
        "k_2": 120,
        "w_1": 0.2,
        "w_2": 0.3,
        "w_3": 0.5,
    }



def test_report_includes_best_trial_and_metrics() -> None:
    from scripts.optimize_retrieval_params import _build_report

    report = _build_report(
        corpus="join",
        tenant_id="benchmark",
        fixture_dir="tests/fixtures/retrieval_bench/join",
        limit=20,
        trials=[
            {
                "number": 0,
                "value": 0.1,
                "params": {"k_1": 120},
                "metrics": {"recall@10": 0.2},
                "timings": {"avg_ms": 1000.0},
            },
            {
                "number": 1,
                "value": 0.5,
                "params": {"k_1": 300},
                "metrics": {"recall@10": 0.6},
                "timings": {"avg_ms": 900.0},
            },
        ],
    )

    assert report["corpus"] == "join"
    assert report["tenant_id"] == "benchmark"
    assert report["limit"] == 20
    assert report["best_trial"]["number"] == 1
    assert report["best_params"] == {"k_1": 300}
    assert report["trials"][0]["metrics"]["recall@10"] == 0.2


def test_run_optimization_calls_benchmark_with_suggested_params(monkeypatch, tmp_path) -> None:
    from scripts.optimize_retrieval_params import run_optimization

    seen: list[dict[str, object]] = []

    def fake_run_retrieval_benchmark(
        fixture_dir,
        *,
        tenant_id,
        corpus,
        limit,
        plan_overrides,
    ):
        seen.append(
            {
                "fixture_dir": fixture_dir,
                "tenant_id": tenant_id,
                "corpus": corpus,
                "limit": limit,
                "plan_overrides": plan_overrides,
            }
        )
        return {
            "metrics": {"recall@10": 0.8},
            "timings": {"avg_ms": 1000.0},
            "layers": {"L3": {"avg_ms": 900.0}},
            "failures": 0,
            "evaluation": {"evaluated_pairs": 4},
        }

    monkeypatch.setattr(
        "scripts.optimize_retrieval_params.run_retrieval_benchmark",
        fake_run_retrieval_benchmark,
    )

    report = run_optimization(
        fixture_dir=tmp_path,
        tenant_id="benchmark",
        corpus="join",
        limit=5,
        trials=1,
        timeout=None,
        seed=42,
        storage=None,
        study_name=None,
        latency_penalty_ms=10_000.0,
        k2_choices=[40, 80, 120],
    )

    assert len(seen) == 1
    assert seen[0]["fixture_dir"] == tmp_path
    assert seen[0]["tenant_id"] == "benchmark"
    assert seen[0]["corpus"] == "join"
    assert seen[0]["limit"] == 5
    assert seen[0]["plan_overrides"] == report["trials"][0]["params"]
    assert report["best_trial"]["value"] == pytest.approx(0.7)
    assert report["trials"][0]["metrics"] == {"recall@10": 0.8}
    assert report["trials"][0]["timings"] == {"avg_ms": 1000.0}
    assert report["trials"][0]["layers"] == {"L3": {"avg_ms": 900.0}}
    assert report["trials"][0]["failures"] == 0
    assert report["trials"][0]["evaluation"] == {"evaluated_pairs": 4}


def test_main_writes_optimization_report(monkeypatch, tmp_path, capsys) -> None:
    from scripts import optimize_retrieval_params

    fixture_dir = tmp_path / "join"
    fixture_dir.mkdir()
    output = tmp_path / "report.json"

    def fake_run_optimization(**kwargs):
        return {
            "corpus": kwargs["corpus"],
            "tenant_id": kwargs["tenant_id"],
            "fixture_dir": str(kwargs["fixture_dir"]),
            "limit": kwargs["limit"],
            "k2_choices": kwargs["k2_choices"],
            "best_trial": None,
            "best_params": {},
            "trials": [],
        }

    monkeypatch.setattr(optimize_retrieval_params, "run_optimization", fake_run_optimization)
    monkeypatch.setattr(
        "sys.argv",
        [
            "optimize_retrieval_params.py",
            str(fixture_dir),
            "--tenant-id",
            "benchmark",
            "--corpus",
            "join",
            "--limit",
            "5",
            "--trials",
            "1",
            "--k2-choices",
            "40,80",
            "--output",
            str(output),
        ],
    )

    optimize_retrieval_params.main()

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert printed == written
    assert written["corpus"] == "join"
    assert written["tenant_id"] == "benchmark"
    assert written["limit"] == 5
    assert written["k2_choices"] == [40, 80]
