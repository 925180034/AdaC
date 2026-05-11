#!/usr/bin/env python3
"""Run retrieval benchmark directly against the Python TLCF agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from statistics import mean, median
from typing import Any, Literal

from qdrant_client import AsyncQdrantClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from adacascade.agents import retrieval
from adacascade.agents.profiling import load_candidate_profiles, load_table_profile
from adacascade.config import settings
from adacascade.db.session import get_session, init_db
from adacascade.indexing.qdrant_client import AdacQdrantClient
from adacascade.indexing.registry import init_qdrant_registry

Corpus = Literal["join", "union"]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ground_truth(path: Path) -> tuple[dict[str, set[str]], dict[str, int]]:
    data = _load_json(path)
    expected: dict[str, set[str]] = {}
    total_pairs = 0
    ignored_self_pairs = 0
    for pair in data.get("pairs", []):
        query_id = str(pair["query_table_id"])
        candidate_id = str(pair["candidate_table_id"])
        total_pairs += 1
        if candidate_id == query_id:
            ignored_self_pairs += 1
            continue
        expected.setdefault(query_id, set()).add(candidate_id)
    return expected, {
        "ground_truth_pairs": total_pairs,
        "ignored_self_pairs": ignored_self_pairs,
        "evaluated_pairs": total_pairs - ignored_self_pairs,
    }


def _fallback_profile(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "table_id": str(query["table_id"]),
        "table_name": str(query.get("table_name") or query["table_id"]),
        "text_blob": str(query.get("table_name") or query["table_id"]),
        "type_multiset": [],
        "columns": [],
    }


def _profiles_from_session(
    query: dict[str, Any], tenant_id: str, db: Session, corpus: Corpus
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    query_id = str(query["table_id"])
    try:
        query_profile = load_table_profile(query_id, db)
    except SQLAlchemyError:
        query_profile = _fallback_profile(query)
    return query_profile, load_candidate_profiles(
        query_id,
        tenant_id,
        db,
        corpus=corpus,
    )


def _profiles(
    query: dict[str, Any], tenant_id: str, corpus: Corpus, db: Session | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if db is not None:
        return _profiles_from_session(query, tenant_id, db, corpus)
    init_db(settings.DATABASE_URL)
    with get_session() as session:
        return _profiles_from_session(query, tenant_id, session, corpus)


def _init_qdrant_registry() -> None:
    init_qdrant_registry(
        AdacQdrantClient(
            AsyncQdrantClient(url=settings.QDRANT_URL, check_compatibility=False)
        )
    )



def _recall(
    results: list[dict[str, Any]], expected: dict[str, set[str]], k: int
) -> float:
    if not results:
        return 0.0
    hits = 0
    for result in results:
        truth = expected.get(str(result["query_table_id"]), set())
        ranking = [str(item["table_id"]) for item in result["ranking"][:k]]
        if truth and any(table_id in truth for table_id in ranking):
            hits += 1
    return hits / len(results)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def _avg_layer_size(results: list[dict[str, Any]], key: str) -> float:
    if not results:
        return 0.0
    return mean(float(len(result.get(key, []))) for result in results)


def _avg_stage_ms(results: list[dict[str, Any]], key: str) -> float:
    values = [
        float(result.get("stage_timings_ms", {}).get(key, 0.0)) for result in results
    ]
    return mean(values) if values else 0.0


def run_retrieval_benchmark(
    fixture_dir: Path,
    *,
    tenant_id: str = settings.DEFAULT_TENANT_ID,
    corpus: Corpus = "join",
    limit: int | None = None,
    top_k: int = 10,
    plan_overrides: dict[str, float | int | bool] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    _init_qdrant_registry()
    queries_data = _load_json(fixture_dir / "queries.json")
    expected, evaluation = _ground_truth(fixture_dir / "ground_truth.json")
    queries = list(queries_data.get("queries", []))
    if limit is not None:
        queries = queries[:limit]

    results: list[dict[str, Any]] = []
    failures = 0
    for query in queries:
        started = time.perf_counter()
        try:
            query_profile, candidate_profiles = _profiles(query, tenant_id, corpus, db)
            state = {
                "task_id": "",
                "tenant_id": tenant_id,
                "task_type": "DISCOVER",
                "subtask": str(queries_data.get("task_type") or corpus.upper()),
                "corpus": corpus,
                "query_profile": query_profile,
                "candidate_profiles": candidate_profiles,
                "plan": dict(plan_overrides or {}),
            }
            output = asyncio.run(retrieval.run(state))
            elapsed_ms = (time.perf_counter() - started) * 1000
            results.append(
                {
                    "query_table_id": str(query["table_id"]),
                    "ranking": list(output.get("ranking", []))[:top_k],
                    "elapsed_ms": elapsed_ms,
                    "c1_meta": list(output.get("c1_meta", [])),
                    "c2_vec": list(output.get("c2_vec", [])),
                    "c3_llm": list(output.get("c3_llm", [])),
                    "stage_timings_ms": dict(output.get("stage_timings_ms", {})),
                }
            )
        except Exception:
            failures += 1

    timings = [float(result["elapsed_ms"]) for result in results]
    task_type = str(queries_data.get("task_type") or corpus.upper())
    return {
        "task_type": task_type,
        "tenant_id": tenant_id,
        "corpus": corpus,
        "queries": len(queries),
        "cache": {"llm_cache_enabled": False},
        "evaluation": evaluation,
        "completed": len(results),
        "failures": failures,
        "metrics": {
            "recall@1": _recall(results, expected, 1),
            "recall@5": _recall(results, expected, 5),
            "recall@10": _recall(results, expected, 10),
        },
        "timings": {
            "avg_ms": mean(timings) if timings else 0.0,
            "p50_ms": median(timings) if timings else 0.0,
            "p95_ms": _percentile(timings, 95),
        },
        "layers": {
            "L1": {
                "avg_output_size": _avg_layer_size(results, "c1_meta"),
                "avg_ms": _avg_stage_ms(results, "L1"),
            },
            "L2": {
                "avg_output_size": _avg_layer_size(results, "c2_vec"),
                "avg_ms": _avg_stage_ms(results, "L2"),
            },
            "L3": {
                "avg_output_size": _avg_layer_size(results, "c3_llm"),
                "avg_ms": _avg_stage_ms(results, "L3"),
            },
            "aggregate": {"avg_ms": _avg_stage_ms(results, "aggregate")},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_dir", type=Path)
    parser.add_argument("--tenant-id", default=settings.DEFAULT_TENANT_ID)
    parser.add_argument("--corpus", choices=["join", "union"], default="join")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--plan-json", help="JSON object with Retrieval plan overrides")
    args = parser.parse_args()

    plan_overrides = json.loads(args.plan_json) if args.plan_json else None
    if plan_overrides is not None and not isinstance(plan_overrides, dict):
        raise SystemExit("--plan-json must be a JSON object")

    report = run_retrieval_benchmark(
        args.fixture_dir,
        tenant_id=args.tenant_id,
        corpus=args.corpus,
        limit=args.limit,
        top_k=args.top_k,
        plan_overrides=plan_overrides,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
