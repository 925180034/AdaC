#!/usr/bin/env python3
"""Optimize Retrieval benchmark parameters with Optuna."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

import optuna

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.run_retrieval_benchmark import run_retrieval_benchmark

Corpus = Literal["join", "union"]
DEFAULT_K2_CHOICES = [40, 80, 120]


def _normalize_weights(raw_w1: float, raw_w2: float, raw_w3: float) -> dict[str, float]:
    total = raw_w1 + raw_w2 + raw_w3
    if total <= 0:
        return {"w_1": 1 / 3, "w_2": 1 / 3, "w_3": 1 / 3}
    return {"w_1": raw_w1 / total, "w_2": raw_w2 / total, "w_3": raw_w3 / total}


def _objective_score(
    *, recall_at_10: float, avg_ms: float, latency_penalty_ms: float
) -> float:
    return recall_at_10 - (avg_ms / latency_penalty_ms)


def _suggest_params(
    trial: Any, *, k2_choices: list[int] | None = None
) -> dict[str, float | int]:
    weights = _normalize_weights(
        trial.suggest_float("raw_w1", 0.01, 1.0),
        trial.suggest_float("raw_w2", 0.01, 1.0),
        trial.suggest_float("raw_w3", 0.01, 1.0),
    )
    return {
        "theta_1": trial.suggest_float("theta_1", 0.05, 0.30),
        "theta_2": trial.suggest_float("theta_2", 0.35, 0.75),
        "theta_3": trial.suggest_float("theta_3", 0.20, 0.70),
        "k_1": trial.suggest_categorical("k_1", [120, 200, 300, 500, 800]),
        "k_2": trial.suggest_categorical("k_2", k2_choices or DEFAULT_K2_CHOICES),
        **weights,
    }



def _trial_report(trial: Any) -> dict[str, Any]:
    return {
        "number": trial.number,
        "value": trial.value,
        "params": dict(trial.user_attrs.get("params", trial.params)),
        "metrics": dict(trial.user_attrs.get("metrics", {})),
        "timings": dict(trial.user_attrs.get("timings", {})),
        "layers": dict(trial.user_attrs.get("layers", {})),
        "failures": trial.user_attrs.get("failures", 0),
        "evaluation": dict(trial.user_attrs.get("evaluation", {})),
    }


def _study_trials(study: Any) -> list[dict[str, Any]]:
    return [
        _trial_report(trial)
        for trial in study.trials
        if trial.value is not None and trial.state == optuna.trial.TrialState.COMPLETE
    ]


def run_optimization(
    *,
    fixture_dir: Path,
    tenant_id: str,
    corpus: Corpus,
    limit: int | None,
    trials: int,
    timeout: int | None,
    seed: int,
    storage: str | None,
    study_name: str | None,
    latency_penalty_ms: float,
    k2_choices: list[int] | None = None,
) -> dict[str, Any]:
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(
        direction="maximize",
        sampler=sampler,
        storage=storage,
        study_name=study_name,
        load_if_exists=bool(storage and study_name),
    )

    def objective(trial: Any) -> float:
        params = _suggest_params(trial, k2_choices=k2_choices)
        benchmark = run_retrieval_benchmark(
            fixture_dir,
            tenant_id=tenant_id,
            corpus=corpus,
            limit=limit,
            plan_overrides=params,
        )
        metrics = dict(benchmark.get("metrics", {}))
        timings = dict(benchmark.get("timings", {}))
        layers = dict(benchmark.get("layers", {}))
        evaluation = dict(benchmark.get("evaluation", {}))
        value = _objective_score(
            recall_at_10=float(metrics.get("recall@10", 0.0)),
            avg_ms=float(timings.get("avg_ms", 0.0)),
            latency_penalty_ms=latency_penalty_ms,
        )
        trial.set_user_attr("params", params)
        trial.set_user_attr("metrics", metrics)
        trial.set_user_attr("timings", timings)
        trial.set_user_attr("layers", layers)
        trial.set_user_attr("failures", int(benchmark.get("failures", 0)))
        trial.set_user_attr("evaluation", evaluation)
        return value

    study.optimize(objective, n_trials=trials, timeout=timeout)
    return _build_report(
        corpus=corpus,
        tenant_id=tenant_id,
        fixture_dir=str(fixture_dir),
        limit=limit,
        trials=_study_trials(study),
    )


def _build_report(
    *,
    corpus: Corpus,
    tenant_id: str,
    fixture_dir: str,
    limit: int | None,
    trials: list[dict[str, Any]],
) -> dict[str, Any]:
    best_trial = max(trials, key=lambda trial: float(trial["value"])) if trials else None
    return {
        "corpus": corpus,
        "tenant_id": tenant_id,
        "fixture_dir": fixture_dir,
        "limit": limit,
        "best_trial": best_trial,
        "best_params": dict(best_trial["params"]) if best_trial else {},
        "trials": trials,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("--tenant-id", default="benchmark")
    parser.add_argument("--corpus", choices=["join", "union"], default="join")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--storage")
    parser.add_argument("--study-name")
    parser.add_argument("--latency-penalty-ms", type=float, default=10_000.0)
    parser.add_argument(
        "--k2-choices",
        default=",".join(str(choice) for choice in DEFAULT_K2_CHOICES),
        help="Comma-separated k_2 categorical choices",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    k2_choices = [int(choice) for choice in args.k2_choices.split(",") if choice]
    report = run_optimization(
        fixture_dir=args.fixture_dir,
        tenant_id=args.tenant_id,
        corpus=args.corpus,
        limit=args.limit,
        trials=args.trials,
        timeout=args.timeout,
        seed=args.seed,
        storage=args.storage,
        study_name=args.study_name,
        latency_penalty_ms=args.latency_penalty_ms,
        k2_choices=k2_choices,
    )
    text = json.dumps(report, sort_keys=True)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
