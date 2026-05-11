from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.db.models import Base, ColumnMetadata, TableRegistry


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _table(table_id: str, *, table_name: str | None = None) -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id="benchmark",
        source_system="retrieval|join",
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_name or table_id,
        row_count=1,
        col_count=1,
        uploaded_at=now,
        updated_at=now,
        status="READY",
    )


def test_retrieval_benchmark_reports_recall_and_timings(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_retrieval_benchmark import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "queries": [
                    {"table_id": "query-1", "table_name": "Query 1"},
                    {"table_id": "query-2", "table_name": "Query 2"},
                ],
            }
        )
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [
                    {"query_table_id": "query-1", "candidate_table_id": "hit-1"},
                    {"query_table_id": "query-2", "candidate_table_id": "missing"},
                ],
            }
        )
    )

    async def fake_run(state):
        ranking = {
            "query-1": [{"table_id": "hit-1", "score": 1.0}],
            "query-2": [{"table_id": "other", "score": 0.5}],
        }[state["query_profile"]["table_id"]]
        return {
            **state,
            "ranking": ranking,
            "c1_meta": ["c1"],
            "c2_vec": ["c2"],
            "c3_llm": [item["table_id"] for item in ranking],
            "stage_timings_ms": {"L1": 1.0, "L2": 2.0, "L3": 3.0, "aggregate": 4.0},
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)

    report = run_retrieval_benchmark(
        fixture_dir,
        tenant_id="benchmark",
        corpus="join",
        limit=2,
        top_k=10,
    )

    assert report["task_type"] == "JOIN"
    assert report["cache"] == {"llm_cache_enabled": False}
    assert report["queries"] == 2
    assert report["failures"] == 0
    assert report["metrics"]["recall@1"] == 0.5
    assert report["metrics"]["recall@5"] == 0.5
    assert report["metrics"]["recall@10"] == 0.5
    assert report["timings"]["avg_ms"] >= 0
    assert report["layers"]["L1"]["avg_output_size"] == 1
    assert report["layers"]["L1"]["avg_ms"] == 1.0
    assert report["layers"]["L2"]["avg_output_size"] == 1
    assert report["layers"]["L2"]["avg_ms"] == 2.0
    assert report["layers"]["L3"]["avg_output_size"] == 1
    assert report["layers"]["L3"]["avg_ms"] == 3.0
    assert report["layers"]["aggregate"]["avg_ms"] == 4.0


def test_retrieval_benchmark_ignores_unretrievable_self_pairs(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_retrieval_benchmark import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps({"task_type": "JOIN", "queries": [{"table_id": "query"}]})
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [
                    {"query_table_id": "query", "candidate_table_id": "query"},
                    {"query_table_id": "query", "candidate_table_id": "hit"},
                ],
            }
        )
    )

    async def fake_run(state):
        return {
            **state,
            "ranking": [{"table_id": "hit", "score": 1.0}],
            "c1_meta": [],
            "c2_vec": [],
            "c3_llm": [],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)

    report = run_retrieval_benchmark(fixture_dir, tenant_id="benchmark", corpus="join")

    assert report["metrics"] == {"recall@1": 1.0, "recall@5": 1.0, "recall@10": 1.0}
    assert report["evaluation"]["ignored_self_pairs"] == 1
    assert report["evaluation"]["ground_truth_pairs"] == 2
    assert report["evaluation"]["evaluated_pairs"] == 1



def test_retrieval_benchmark_passes_corpus_to_retrieval_state(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_retrieval_benchmark import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "union"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps({"task_type": "UNION", "queries": [{"table_id": "query"}]})
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "UNION",
                "pairs": [
                    {"query_table_id": "query", "candidate_table_id": "candidate"}
                ],
            }
        )
    )
    seen: dict[str, object] = {}

    async def fake_run(state):
        seen["corpus"] = state.get("corpus")
        return {
            **state,
            "ranking": [{"table_id": "candidate", "score": 1.0}],
            "c1_meta": [],
            "c2_vec": [],
            "c3_llm": [],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)

    run_retrieval_benchmark(fixture_dir, tenant_id="benchmark", corpus="union")

    assert seen["corpus"] == "union"


def test_retrieval_benchmark_passes_plan_overrides_to_retrieval_state(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_retrieval_benchmark import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps({"task_type": "JOIN", "queries": [{"table_id": "query"}]})
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [
                    {"query_table_id": "query", "candidate_table_id": "candidate"}
                ],
            }
        )
    )
    seen: dict[str, object] = {}

    async def fake_run(state):
        seen["plan"] = state.get("plan")
        return {
            **state,
            "ranking": [{"table_id": "candidate", "score": 1.0}],
            "c1_meta": [],
            "c2_vec": [],
            "c3_llm": [],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)

    run_retrieval_benchmark(
        fixture_dir,
        tenant_id="benchmark",
        corpus="join",
        plan_overrides={"k_1": 300, "theta_2": 0.4},
    )

    assert seen["plan"] == {"k_1": 300, "theta_2": 0.4}



def test_candidate_profiles_can_scope_to_retrieval_corpus(tmp_path: Path) -> None:
    from adacascade.agents.profiling import load_candidate_profiles

    db = _session(tmp_path)
    db.add(_table("query"))
    db.add(_table("join-candidate"))
    union_candidate = _table("union-candidate")
    union_candidate.source_system = "retrieval|union"
    schema_candidate = _table("schema-candidate")
    schema_candidate.source_system = "mimic_omop"
    db.add(union_candidate)
    db.add(schema_candidate)
    db.commit()

    profiles = load_candidate_profiles("query", "benchmark", db, corpus="join")

    assert list(profiles) == ["join-candidate"]



def test_candidate_profiles_do_not_encode_table_vectors(
    tmp_path: Path, monkeypatch
) -> None:
    from adacascade.agents.profiling import load_candidate_profiles

    db = _session(tmp_path)
    db.add_all([_table("query", table_name="Query"), _table("candidate", table_name="Candidate")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="query:0:id",
                table_id="query",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="candidate:0:id",
                table_id="candidate",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
        ]
    )
    db.commit()

    def fail_encode(table_name, columns):
        raise AssertionError("candidate profiles should not encode table vectors")

    monkeypatch.setattr("adacascade.agents.profiling.encode_table_vector", fail_encode)

    profiles = load_candidate_profiles("query", "benchmark", db)

    assert list(profiles) == ["candidate"]
    assert "table_vector" not in profiles["candidate"]



def test_loaded_profile_restores_sample_values_from_stat_summary(
    tmp_path: Path, monkeypatch
) -> None:
    from adacascade.agents.profiling import load_table_profile

    db = _session(tmp_path)
    db.add(_table("query", table_name="Query"))
    db.add(
        ColumnMetadata(
            column_id="query:0:id",
            table_id="query",
            ordinal=0,
            col_name="id",
            col_type="str",
            stat_summary=json.dumps({"sample_values": ["a", "b", "c"]}),
        )
    )
    db.commit()
    monkeypatch.setattr("adacascade.agents.profiling.encode_table_vector", lambda *_: [])

    profile = load_table_profile("query", db)

    assert profile["columns"][0]["sample_values"] == ["a", "b", "c"]



def test_l3_prompt_includes_column_sample_values() -> None:
    from adacascade.agents.retrieval.layer3 import _build_batch_prompt

    messages = _build_batch_prompt(
        "patients",
        [{"name": "patient_id", "dtype": "str", "sample_values": ["p1", "p2"]}],
        [
            {
                "table_name": "people",
                "columns": [
                    {"name": "person_id", "dtype": "str", "sample_values": ["p1", "p3"]}
                ],
            }
        ],
        "JOIN",
        0,
    )

    prompt = "\n".join(message["content"] for message in messages)
    assert "samples: [p1, p2]" in prompt
    assert "samples: [p1, p3]" in prompt



def test_l3_prompt_truncates_long_sample_values() -> None:
    from adacascade.agents.retrieval.layer3 import _column_prompt

    prompt = _column_prompt(
        {
            "name": "description",
            "dtype": "str",
            "sample_values": ["x" * 100, "y" * 100, "z" * 100],
        }
    )

    assert len(prompt) < 120
    assert "xxx" in prompt
    assert "yyy" in prompt



def test_l3_batches_one_candidate_per_call_for_local_context() -> None:
    from adacascade.agents.retrieval.layer3 import _candidate_batches

    candidates = [{"table_id": str(index)} for index in range(3)]

    batches = _candidate_batches(candidates, batch_size=10)

    assert batches == [([candidates[0]], 0), ([candidates[1]], 1), ([candidates[2]], 2)]



def test_loaded_retrieval_profile_includes_table_vector(
    tmp_path: Path, monkeypatch
) -> None:
    from adacascade.agents.profiling import load_table_profile

    db = _session(tmp_path)
    db.add(_table("query", table_name="Query"))
    db.add(
        ColumnMetadata(
            column_id="query:0:id",
            table_id="query",
            ordinal=0,
            col_name="id",
            col_type="int",
        )
    )
    db.commit()

    monkeypatch.setattr(
        "adacascade.agents.profiling.encode_table_vector",
        lambda table_name, columns: [0.1, 0.2, 0.3],
    )

    profile = load_table_profile("query", db)

    assert profile["table_vector"] == [0.1, 0.2, 0.3]



def test_retrieval_benchmark_loads_profiles_from_db(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_retrieval_benchmark import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "queries": [{"table_id": "query", "table_name": "Query"}],
            }
        )
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [
                    {"query_table_id": "query", "candidate_table_id": "candidate"}
                ],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all([_table("query"), _table("candidate")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="query:0:id",
                table_id="query",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="candidate:0:id",
                table_id="candidate",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
        ]
    )
    db.commit()
    seen: dict[str, object] = {}

    async def fake_run(state):
        seen["query_profile"] = state["query_profile"]
        seen["candidate_profiles"] = state["candidate_profiles"]
        return {
            **state,
            "ranking": [{"table_id": "candidate", "score": 1.0}],
            "c1_meta": ["candidate"],
            "c2_vec": ["candidate"],
            "c3_llm": ["candidate"],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)

    report = run_retrieval_benchmark(
        fixture_dir,
        tenant_id="benchmark",
        corpus="join",
        db=db,
    )

    assert report["metrics"]["recall@1"] == 1.0
    assert seen["query_profile"]["table_id"] == "query"
    assert list(seen["candidate_profiles"].keys()) == ["candidate"]


def test_retrieval_benchmark_initializes_qdrant_registry(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps({"task_type": "JOIN", "queries": [{"table_id": "query"}]})
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [{"query_table_id": "query", "candidate_table_id": "candidate"}],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all([_table("query"), _table("candidate")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="query:0:id",
                table_id="query",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="candidate:0:id",
                table_id="candidate",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
        ]
    )
    db.commit()
    seen: dict[str, object] = {}

    class FakeAsyncQdrantClient:
        def __init__(self, *, url: str, check_compatibility: bool) -> None:
            seen["url"] = url
            seen["check_compatibility"] = check_compatibility

    async def fake_run(state):
        return {
            **state,
            "ranking": [{"table_id": "candidate", "score": 1.0}],
            "c1_meta": ["candidate"],
            "c2_vec": ["candidate"],
            "c3_llm": ["candidate"],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)
    monkeypatch.setattr(run_retrieval_benchmark, "AsyncQdrantClient", FakeAsyncQdrantClient)
    monkeypatch.setattr(run_retrieval_benchmark.settings, "QDRANT_URL", "http://qdrant.test")
    monkeypatch.setattr(
        run_retrieval_benchmark,
        "AdacQdrantClient",
        lambda client: {"client": client},
    )
    monkeypatch.setattr(
        run_retrieval_benchmark,
        "init_qdrant_registry",
        lambda client: seen.setdefault("registry", client),
    )

    run_retrieval_benchmark.run_retrieval_benchmark(
        fixture_dir,
        tenant_id="benchmark",
        corpus="join",
        db=db,
    )

    assert seen["url"] == "http://qdrant.test"
    assert seen["check_compatibility"] is False
    assert seen["registry"]



def test_retrieval_benchmark_uses_settings_database_when_db_is_not_passed(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts import run_retrieval_benchmark

    fixture_dir = tmp_path / "bench" / "join"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "queries.json").write_text(
        json.dumps({"task_type": "JOIN", "queries": [{"table_id": "query"}]})
    )
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "pairs": [
                    {"query_table_id": "query", "candidate_table_id": "candidate"}
                ],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all([_table("query"), _table("candidate")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="query:0:id",
                table_id="query",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="candidate:0:id",
                table_id="candidate",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
        ]
    )
    db.commit()
    db.close()
    seen: dict[str, object] = {}

    async def fake_run(state):
        seen["candidate_profiles"] = state["candidate_profiles"]
        return {
            **state,
            "ranking": [{"table_id": "candidate", "score": 1.0}],
            "c1_meta": ["candidate"],
            "c2_vec": ["candidate"],
            "c3_llm": ["candidate"],
        }

    monkeypatch.setattr("adacascade.agents.retrieval.run", fake_run)
    monkeypatch.setattr(
        run_retrieval_benchmark.settings,
        "DATABASE_URL",
        f"sqlite:///{tmp_path / 'metadata.db'}",
    )

    report = run_retrieval_benchmark.run_retrieval_benchmark(
        fixture_dir,
        tenant_id="benchmark",
        corpus="join",
    )

    assert report["metrics"]["recall@1"] == 1.0
    assert list(seen["candidate_profiles"].keys()) == ["candidate"]


def test_matcher_benchmark_does_not_encode_table_vectors(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_matcher_benchmark import run_matcher_benchmark

    fixture_dir = tmp_path / "matcher" / "wikidata" / "joinable"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "scenario": "SLD",
                "source_table_id": "source",
                "target_table_id": "target",
                "column_matches": [{"source_column": "id", "target_column": "person_id"}],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all([_table("source"), _table("target")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="source:0:id",
                table_id="source",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="target:0:person_id",
                table_id="target",
                ordinal=0,
                col_name="person_id",
                col_type="int",
            ),
        ]
    )
    db.commit()

    def fail_encode(table_name, columns):
        raise AssertionError("matcher profiles should not encode table vectors")

    async def fake_run(state):
        return {
            **state,
            "final_mappings": [
                {
                    "source_table_id": "source",
                    "source_column": "id",
                    "target_table_id": "target",
                    "target_column": "person_id",
                }
            ],
            "similarity_pairs": [],
        }

    monkeypatch.setattr("adacascade.agents.profiling.encode_table_vector", fail_encode)
    monkeypatch.setattr("adacascade.agents.matcher.run", fake_run)

    report = run_matcher_benchmark(fixture_dir, tenant_id="benchmark", db=db)

    assert report["metrics"]["recall"] == 1.0



def test_matcher_benchmark_reports_precision_recall_f1(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_matcher_benchmark import run_matcher_benchmark

    fixture_dir = tmp_path / "matcher" / "wikidata" / "joinable"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "JOIN",
                "scenario": "SLD",
                "source_table_id": "source",
                "target_table_id": "target",
                "column_matches": [
                    {"source_column": "id", "target_column": "person_id"},
                    {"source_column": "name", "target_column": "person_name"},
                ],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all([_table("source"), _table("target")])
    db.add_all(
        [
            ColumnMetadata(
                column_id="source:0:id",
                table_id="source",
                ordinal=0,
                col_name="id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="source:1:name",
                table_id="source",
                ordinal=1,
                col_name="name",
                col_type="str",
            ),
            ColumnMetadata(
                column_id="target:0:person_id",
                table_id="target",
                ordinal=0,
                col_name="person_id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="target:1:person_name",
                table_id="target",
                ordinal=1,
                col_name="person_name",
                col_type="str",
            ),
        ]
    )
    db.commit()

    async def fake_run(state):
        return {
            **state,
            "final_mappings": [
                {
                    "source_table_id": "source",
                    "source_column": "id",
                    "target_table_id": "target",
                    "target_column": "person_id",
                },
                {
                    "source_table_id": "source",
                    "source_column": "name",
                    "target_table_id": "target",
                    "target_column": "wrong",
                },
            ],
            "similarity_pairs": [{"src_idx": 0}, {"src_idx": 1}, {"src_idx": 2}],
            "stage_timings_ms": {
                "candidate_filtering": 1.0,
                "llm_verification": 2.0,
                "decision": 3.0,
            },
        }

    monkeypatch.setattr("adacascade.agents.matcher.run", fake_run)

    report = run_matcher_benchmark(fixture_dir, tenant_id="benchmark", db=db)

    assert report["scenario"] == "SLD"
    assert report["cache"] == {"llm_cache_enabled": False}
    assert report["pairs"] == 1
    assert report["failures"] == 0
    assert report["metrics"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert report["timings"]["avg_ms"] >= 0
    assert report["stages"]["candidate_filtering"]["pairs"] == 3
    assert report["stages"]["candidate_filtering"]["avg_ms"] == 1.0
    assert report["stages"]["llm_verification"]["avg_ms"] == 2.0
    assert report["stages"]["decision"]["avg_ms"] == 3.0


def test_matcher_benchmark_supports_mimic_omop_schema_pairs(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_matcher_benchmark import run_matcher_benchmark

    fixture_dir = tmp_path / "matcher" / "mimic_omop"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "task_type": "MATCH_ONLY",
                "scenario": "SMD",
                "column_matches": [
                    {
                        "source_table": "ADMISSIONS",
                        "source_column": "SUBJECT_ID",
                        "target_table": "PERSON",
                        "target_column": "person_id",
                    },
                    {
                        "source_table": "ADMISSIONS",
                        "source_column": "HADM_ID",
                        "target_table": "VISIT_OCCURRENCE",
                        "target_column": "visit_occurrence_id",
                    },
                    {
                        "source_table": "PATIENTS",
                        "source_column": "SUBJECT_ID",
                        "target_table": "PERSON",
                        "target_column": "person_id",
                    },
                    {
                        "source_table": "ADMISSIONS",
                        "source_column": "IGNORED",
                        "target_table": "nan",
                        "target_column": "nan",
                    },
                    {
                        "source_table": "ADMISSIONS",
                        "source_column": "IGNORED_ZERO",
                        "target_table": "0",
                        "target_column": "0",
                    },
                ],
            }
        )
    )
    db = _session(tmp_path)
    db.add_all(
        [
            _table("mimic:ADMISSIONS", table_name="ADMISSIONS"),
            _table("mimic:PATIENTS", table_name="PATIENTS"),
            _table("omop:PERSON", table_name="PERSON"),
            _table("omop:VISIT_OCCURRENCE", table_name="VISIT_OCCURRENCE"),
        ]
    )
    db.add_all(
        [
            ColumnMetadata(
                column_id="mimic:ADMISSIONS:0:SUBJECT_ID",
                table_id="mimic:ADMISSIONS",
                ordinal=0,
                col_name="SUBJECT_ID",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="mimic:ADMISSIONS:1:HADM_ID",
                table_id="mimic:ADMISSIONS",
                ordinal=1,
                col_name="HADM_ID",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="mimic:PATIENTS:0:SUBJECT_ID",
                table_id="mimic:PATIENTS",
                ordinal=0,
                col_name="SUBJECT_ID",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="omop:PERSON:0:person_id",
                table_id="omop:PERSON",
                ordinal=0,
                col_name="person_id",
                col_type="int",
            ),
            ColumnMetadata(
                column_id="omop:VISIT_OCCURRENCE:0:visit_occurrence_id",
                table_id="omop:VISIT_OCCURRENCE",
                ordinal=0,
                col_name="visit_occurrence_id",
                col_type="int",
            ),
        ]
    )
    db.commit()

    async def fake_run(state):
        source_name = state["query_profile"]["table_name"]
        target_name = state["target_profile"]["table_name"]
        target_column = {
            "PERSON": "person_id",
            "VISIT_OCCURRENCE": "visit_occurrence_id",
        }[target_name]
        source_column = {
            ("ADMISSIONS", "PERSON"): "SUBJECT_ID",
            ("PATIENTS", "PERSON"): "SUBJECT_ID",
            ("ADMISSIONS", "VISIT_OCCURRENCE"): "HADM_ID",
        }[(source_name, target_name)]
        return {
            **state,
            "final_mappings": [
                {
                    "source_table_name": source_name,
                    "source_column": source_column,
                    "target_table_name": target_name,
                    "target_column": target_column,
                }
            ],
            "similarity_pairs": [{"src_idx": 0}],
            "stage_timings_ms": {
                "candidate_filtering": 1.0,
                "llm_verification": 2.0,
                "decision": 3.0,
            },
        }

    monkeypatch.setattr("adacascade.agents.matcher.run", fake_run)

    report = run_matcher_benchmark(fixture_dir, tenant_id="benchmark", db=db)

    assert report["scenario"] == "SMD"
    assert report["pairs"] == 3
    assert report["expected_pairs"] == 3
    assert report["metrics"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert report["stages"]["candidate_filtering"]["pairs"] == 3
    assert report["stages"]["llm_verification"]["avg_ms"] == 2.0


def test_matcher_benchmark_runs_all_child_ground_truth_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.run_matcher_benchmark import run_matcher_benchmark

    root = tmp_path / "matcher" / "wikidata"
    for scenario in ["joinable", "unionable"]:
        scenario_dir = root / scenario
        scenario_dir.mkdir(parents=True)
        (scenario_dir / "ground_truth.json").write_text(
            json.dumps(
                {
                    "task_type": "JOIN",
                    "scenario": "SLD",
                    "source_table_id": f"source-{scenario}",
                    "target_table_id": f"target-{scenario}",
                    "column_matches": [
                        {"source_column": "id", "target_column": "person_id"}
                    ],
                }
            )
        )

    db = _session(tmp_path)
    for scenario in ["joinable", "unionable"]:
        db.add_all([_table(f"source-{scenario}"), _table(f"target-{scenario}")])
        db.add_all(
            [
                ColumnMetadata(
                    column_id=f"source-{scenario}:0:id",
                    table_id=f"source-{scenario}",
                    ordinal=0,
                    col_name="id",
                    col_type="int",
                ),
                ColumnMetadata(
                    column_id=f"target-{scenario}:0:person_id",
                    table_id=f"target-{scenario}",
                    ordinal=0,
                    col_name="person_id",
                    col_type="int",
                ),
            ]
        )
    db.commit()

    async def fake_run(state):
        return {
            **state,
            "final_mappings": [
                {
                    "source_table_id": state["query_profile"]["table_id"],
                    "source_column": "id",
                    "target_table_id": state["target_profile"]["table_id"],
                    "target_column": "person_id",
                }
            ],
            "similarity_pairs": [{"src_idx": 0}],
            "stage_timings_ms": {
                "candidate_filtering": 1.0,
                "llm_verification": 2.0,
                "decision": 3.0,
            },
        }

    monkeypatch.setattr("adacascade.agents.matcher.run", fake_run)

    report = run_matcher_benchmark(root, tenant_id="benchmark", db=db)

    assert report["scenarios"] == ["joinable", "unionable"]
    assert report["pairs"] == 2
    assert report["metrics"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_start_llm_defaults_fit_local_4090_kv_cache() -> None:
    script = Path("scripts/start_llm.sh").read_text()

    assert 'VLLM_GPU_MEMORY_UTILIZATION:-0.55' in script
    assert 'VLLM_MAX_MODEL_LEN:-4096' in script



def test_retrieval_benchmark_cli_imports_project_package() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_retrieval_benchmark.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "fixture_dir" in result.stdout


def test_matcher_benchmark_cli_imports_project_package() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_matcher_benchmark.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "fixture_dir" in result.stdout
