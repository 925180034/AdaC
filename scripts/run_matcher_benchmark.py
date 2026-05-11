#!/usr/bin/env python3
"""Run matcher benchmark directly against the Python Matcher agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from statistics import mean, median
from typing import Any

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from adacascade.agents import matcher
from adacascade.db.models import TableRegistry
from adacascade.agents.profiling import load_table_profile
from adacascade.config import settings
from adacascade.db.session import get_session, init_db


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


PairKey = tuple[str, str, str, str]


def _expected_pairs(items: list[dict[str, Any]]) -> set[PairKey]:
    return {
        (
            str(item.get("source_table") or item.get("source_table_id") or ""),
            str(item["source_column"]),
            str(item.get("target_table") or item.get("target_table_id") or ""),
            str(item["target_column"]),
        )
        for item in items
        if _has_target(item)
    }


def _has_target(item: dict[str, Any]) -> bool:
    target_table = str(item.get("target_table", "valid")).lower()
    target_column = str(item.get("target_column", "valid")).lower()
    return target_table not in {"", "nan", "0"} and target_column not in {
        "",
        "nan",
        "0",
    }


def _predicted_pairs(mappings: list[dict[str, Any]]) -> set[PairKey]:
    return {
        (
            str(item.get("source_table_name") or item.get("source_table_id") or ""),
            str(item["source_column"]),
            str(item.get("target_table_name") or item.get("target_table_id") or ""),
            str(item["target_column"]),
        )
        for item in mappings
    }


def _metrics(predicted: set[PairKey], expected: set[PairKey]) -> dict[str, float]:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def _stage_ms(timings: dict[str, float], key: str) -> float:
    return float(timings.get(key, 0.0))


def _load_profiles(
    source_id: str, target_id: str, db: Session | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    if db is not None:
        return load_table_profile(
            source_id, db, include_vector=False
        ), load_table_profile(target_id, db, include_vector=False)
    init_db(settings.DATABASE_URL)
    with get_session() as session:
        return load_table_profile(
            source_id, session, include_vector=False
        ), load_table_profile(target_id, session, include_vector=False)


def _table_id_by_name(db: Session, tenant_id: str, table_name: str, prefix: str) -> str:
    table = (
        db.query(TableRegistry)
        .filter_by(tenant_id=tenant_id, table_name=table_name)
        .filter(TableRegistry.table_id.like(f"{prefix}:%"))
        .one()
    )
    return str(table.table_id)


def _benchmark_cases(
    truth: dict[str, Any], tenant_id: str, db: Session | None
) -> list[dict[str, Any]]:
    if "source_table_id" in truth and "target_table_id" in truth:
        expected_items = [
            {
                "source_table_id": str(truth["source_table_id"]),
                "target_table_id": str(truth["target_table_id"]),
                **item,
            }
            for item in truth.get("column_matches", [])
        ]
        return [
            {
                "source_id": str(truth["source_table_id"]),
                "target_id": str(truth["target_table_id"]),
                "expected_items": expected_items,
            }
        ]

    close_session = False
    if db is None:
        init_db(settings.DATABASE_URL)
        session_context = get_session()
        db = session_context.__enter__()
        close_session = True
    else:
        session_context = None

    try:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in truth.get("column_matches", []):
            if not _has_target(item):
                continue
            key = (str(item["source_table"]), str(item["target_table"]))
            grouped.setdefault(key, []).append(item)
        return [
            {
                "source_id": _table_id_by_name(db, tenant_id, source_name, "mimic"),
                "target_id": _table_id_by_name(db, tenant_id, target_name, "omop"),
                "expected_items": items,
            }
            for (source_name, target_name), items in sorted(grouped.items())
        ]
    finally:
        if close_session and session_context is not None:
            session_context.__exit__(None, None, None)


def _truth_dirs(fixture_dir: Path) -> list[Path]:
    if (fixture_dir / "ground_truth.json").exists():
        return [fixture_dir]
    return sorted(path.parent for path in fixture_dir.glob("*/ground_truth.json"))


def run_matcher_benchmark(
    fixture_dir: Path,
    *,
    tenant_id: str = settings.DEFAULT_TENANT_ID,
    db: Session | None = None,
) -> dict[str, Any]:
    if not (fixture_dir / "ground_truth.json").exists():
        reports = [
            run_matcher_benchmark(path, tenant_id=tenant_id, db=db)
            for path in _truth_dirs(fixture_dir)
        ]
        timings = [float(report["timings"]["avg_ms"]) for report in reports]
        predicted_count = sum(
            int(report["stages"]["decision"]["mappings"]) for report in reports
        )
        expected_count = sum(int(report["expected_pairs"]) for report in reports)
        true_positive = sum(int(report["true_positive"]) for report in reports)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / expected_count if expected_count else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        return {
            "scenario": "aggregate",
            "scenarios": [path.name for path in _truth_dirs(fixture_dir)],
            "task_type": "MATCH_ONLY",
            "tenant_id": tenant_id,
            "pairs": sum(int(report["pairs"]) for report in reports),
            "expected_pairs": expected_count,
            "true_positive": true_positive,
            "cache": {"llm_cache_enabled": False},
            "failures": sum(int(report["failures"]) for report in reports),
            "metrics": {"precision": precision, "recall": recall, "f1": f1},
            "timings": {
                "avg_ms": mean(timings) if timings else 0.0,
                "p50_ms": median(timings) if timings else 0.0,
                "p95_ms": _percentile(timings, 95),
            },
            "stages": {
                "candidate_filtering": {
                    "pairs": sum(
                        int(report["stages"]["candidate_filtering"]["pairs"])
                        for report in reports
                    ),
                    "avg_ms": mean(
                        float(report["stages"]["candidate_filtering"]["avg_ms"])
                        for report in reports
                    )
                    if reports
                    else 0.0,
                },
                "llm_verification": {
                    "pairs": sum(
                        int(report["stages"]["llm_verification"]["pairs"])
                        for report in reports
                    ),
                    "avg_ms": mean(
                        float(report["stages"]["llm_verification"]["avg_ms"])
                        for report in reports
                    )
                    if reports
                    else 0.0,
                },
                "decision": {
                    "mappings": predicted_count,
                    "avg_ms": mean(
                        float(report["stages"]["decision"]["avg_ms"])
                        for report in reports
                    )
                    if reports
                    else 0.0,
                },
            },
        }

    truth = _load_json(fixture_dir / "ground_truth.json")
    cases = _benchmark_cases(truth, tenant_id, db)
    failures = 0
    mappings: list[dict[str, Any]] = []
    similarity_pair_count = 0
    timing_values: list[float] = []
    stage_timing_values: dict[str, list[float]] = {
        "candidate_filtering": [],
        "llm_verification": [],
        "decision": [],
    }
    expected_items: list[dict[str, Any]] = []

    for case in cases:
        expected_items.extend(case["expected_items"])
        started = time.perf_counter()
        try:
            source_profile, target_profile = _load_profiles(
                str(case["source_id"]), str(case["target_id"]), db
            )
            output = asyncio.run(
                matcher.run(
                    {
                        "task_id": "",
                        "tenant_id": tenant_id,
                        "task_type": "MATCH_ONLY",
                        "subtask": str(truth.get("task_type", "JOIN")),
                        "scenario": str(truth.get("scenario", "")),
                        "query_profile": source_profile,
                        "target_profile": target_profile,
                    }
                )
            )
            mappings.extend(list(output.get("final_mappings", [])))
            similarity_pair_count += len(list(output.get("similarity_pairs", [])))
            stage_timings_ms = dict(output.get("stage_timings_ms", {}))
            for key in stage_timing_values:
                stage_timing_values[key].append(float(stage_timings_ms.get(key, 0.0)))
            timing_values.append((time.perf_counter() - started) * 1000)
        except Exception:
            failures += 1

    expected = _expected_pairs(expected_items)
    predicted = _predicted_pairs(mappings)
    true_positive = len(predicted & expected)
    return {
        "scenario": str(truth.get("scenario", "")),
        "task_type": str(truth.get("task_type", "MATCH_ONLY")),
        "tenant_id": tenant_id,
        "pairs": len(cases),
        "expected_pairs": len(expected),
        "true_positive": true_positive,
        "cache": {"llm_cache_enabled": False},
        "failures": failures,
        "metrics": _metrics(predicted, expected),
        "timings": {
            "avg_ms": mean(timing_values) if timing_values else 0.0,
            "p50_ms": median(timing_values) if timing_values else 0.0,
            "p95_ms": _percentile(timing_values, 95),
        },
        "stages": {
            "candidate_filtering": {
                "pairs": similarity_pair_count,
                "avg_ms": mean(stage_timing_values["candidate_filtering"])
                if stage_timing_values["candidate_filtering"]
                else 0.0,
            },
            "llm_verification": {
                "pairs": len(mappings),
                "avg_ms": mean(stage_timing_values["llm_verification"])
                if stage_timing_values["llm_verification"]
                else 0.0,
            },
            "decision": {
                "mappings": len(mappings),
                "avg_ms": mean(stage_timing_values["decision"])
                if stage_timing_values["decision"]
                else 0.0,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("--tenant-id", default=settings.DEFAULT_TENANT_ID)
    args = parser.parse_args()

    report = run_matcher_benchmark(args.fixture_dir, tenant_id=args.tenant_id)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
