# tests/unit/test_retrieval.py
import asyncio
from types import SimpleNamespace

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


def test_build_c1_can_boost_join_candidates_by_sample_overlap(monkeypatch) -> None:
    from adacascade.agents.retrieval import layer1

    class FakeVectorizer:
        def transform(self, values):
            return values

    monkeypatch.setattr(layer1, "load_tfidf", lambda **kwargs: FakeVectorizer())
    class FakeSimilarity:
        def __getitem__(self, key):
            assert key == (0, 0)
            return 0.0

    monkeypatch.setattr(layer1, "cosine_similarity", lambda left, right: FakeSimilarity())

    result = layer1.build_c1(
        "query weak text",
        ["str"],
        [
            {
                "table_id": "candidate",
                "text_blob": "candidate weak text",
                "type_multiset": ["str"],
                "columns": [{"name": "different_key", "sample_values": ["Alpha"]}],
            }
        ],
        theta_1=0.5,
        k_1=10,
        query_columns=[{"name": "join_id", "sample_values": ["alpha"]}],
        join_sample_boost_enabled=True,
        join_sample_boost_weight=0.4,
    )

    assert result == [{"table_id": "candidate", "s1": pytest.approx(0.7)}]


def test_retrieval_run_passes_sample_boost_plan_to_layer1(monkeypatch) -> None:
    from adacascade.agents import retrieval

    seen: dict[str, object] = {}

    def fake_build_c1(*args, **kwargs):
        seen["query_columns"] = kwargs.get("query_columns")
        seen["join_sample_boost_enabled"] = kwargs.get("join_sample_boost_enabled")
        seen["join_sample_boost_weight"] = kwargs.get("join_sample_boost_weight")
        return []

    monkeypatch.setattr(retrieval, "build_c1", fake_build_c1)

    asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "q",
                    "text_blob": "q",
                    "type_multiset": [],
                    "columns": [{"name": "id", "sample_values": ["1"]}],
                },
                "candidate_profiles": {
                    "c": {"table_id": "c", "text_blob": "c", "type_multiset": []}
                },
                "plan": {
                    "join_sample_boost_enabled": True,
                    "join_sample_boost_weight": 0.4,
                },
            }
        )
    )

    assert seen == {
        "query_columns": [{"name": "id", "sample_values": ["1"]}],
        "join_sample_boost_enabled": True,
        "join_sample_boost_weight": 0.4,
    }


def test_retrieval_run_passes_scoped_tfidf_to_layer1(monkeypatch) -> None:
    from adacascade.agents import retrieval

    seen: dict[str, object] = {}

    def fake_build_c1(*args, **kwargs):
        seen["tenant_id"] = kwargs.get("tenant_id")
        seen["corpus"] = kwargs.get("corpus")
        return []

    monkeypatch.setattr(retrieval, "build_c1", fake_build_c1)

    result = asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "union",
                "query_profile": {
                    "table_id": "q",
                    "text_blob": "q",
                    "type_multiset": [],
                },
                "candidate_profiles": {
                    "c": {"table_id": "c", "text_blob": "c", "type_multiset": []}
                },
                "plan": {},
            }
        )
    )

    assert seen == {"tenant_id": "benchmark", "corpus": "union"}
    assert result["ranking"] == []


@pytest.mark.anyio
async def test_retrieval_run_returns_stage_timings(monkeypatch) -> None:
    from adacascade.agents import retrieval

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "candidate", "s1": 0.8}],
    )

    async def fake_search_and_build_c2(*args, **kwargs):
        return [{"table_id": "candidate", "s1": 0.8, "s2": 0.9}], False

    async def fake_batch_verify(*args, **kwargs):
        return [{"table_id": "candidate", "s1": 0.8, "s2": 0.9, "s3": 0.95}]

    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)
    monkeypatch.setattr(retrieval, "batch_verify", fake_batch_verify)

    result = await retrieval.run(
        {
            "task_id": "",
            "tenant_id": "benchmark",
            "query_profile": {
                "table_id": "query",
                "text_blob": "query",
                "type_multiset": [],
                "table_vector": [0.1, 0.2],
            },
            "candidate_profiles": {
                "candidate": {
                    "table_id": "candidate",
                    "text_blob": "candidate",
                    "type_multiset": [],
                }
            },
            "plan": {},
        }
    )

    assert set(result["stage_timings_ms"]) == {"L1", "L2", "L3", "aggregate"}
    assert all(value >= 0 for value in result["stage_timings_ms"].values())


def test_column_recall_keeps_only_candidate_pool_tables(monkeypatch) -> None:
    from adacascade.agents import retrieval

    class FakeQdrant:
        async def search_columns(self, **kwargs):
            return [
                {"table_id": "kept", "score": 0.9},
                {"table_id": "outside", "score": 1.0},
            ]

    monkeypatch.setattr(retrieval, "get_qdrant", lambda: FakeQdrant())
    monkeypatch.setattr(retrieval, "_column_vector", lambda table_name, column: [0.1])

    result = asyncio.run(
        retrieval.recall_tables_by_columns(
            query_profile={
                "table_name": "query",
                "columns": [{"name": "id", "dtype": "str"}],
            },
            tenant_id="benchmark",
            top_k=10,
            source_system="retrieval|join",
            candidate_profiles={"kept": {"table_id": "kept"}},
        )
    )

    assert result == [{"table_id": "kept", "s1": 0.9}]


def test_retrieval_run_keeps_column_recall_out_of_c1(monkeypatch) -> None:
    from adacascade.agents import retrieval

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "lexical", "s1": 0.8}],
    )

    async def fake_recall_by_columns(**kwargs):
        seen["column_recall"] = kwargs
        return [{"table_id": "semantic", "s1": 0.35}]

    async def fake_search_and_build_c2(*, c1, **kwargs):
        seen["c1"] = c1
        return [{"table_id": "lexical", "s1": 0.8, "s2": 0.9}], False

    monkeypatch.setattr(retrieval, "recall_tables_by_columns", fake_recall_by_columns)
    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)

    asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "query",
                    "table_name": "query_table",
                    "text_blob": "query",
                    "type_multiset": [],
                    "table_vector": [0.1, 0.2],
                    "columns": [{"name": "join_key", "dtype": "str"}],
                },
                "candidate_profiles": {
                    "lexical": {"table_id": "lexical", "text_blob": "l", "type_multiset": []},
                    "semantic": {"table_id": "semantic", "text_blob": "s", "type_multiset": []},
                },
                "plan": {"column_recall_enabled": True, "column_recall_top_k": 10},
            }
        )
    )

    assert seen["column_recall"]["source_system"] == "retrieval|join"
    assert seen["c1"] == [{"table_id": "lexical", "s1": 0.8}]


def test_retrieval_run_limits_column_recall_additions(monkeypatch) -> None:
    from adacascade.agents import retrieval

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "lexical", "s1": 0.8}],
    )
    monkeypatch.setattr(
        retrieval,
        "recall_tables_by_columns",
        lambda **kwargs: asyncio.sleep(
            0,
            result=[
                {"table_id": "semantic_1", "s1": 0.35, "s2": 0.35},
                {"table_id": "semantic_2", "s1": 0.34, "s2": 0.34},
            ],
        ),
    )

    async def fake_search_and_build_c2(*args, **kwargs):
        return [{"table_id": "lexical", "s1": 0.8, "s2": 0.9}], False

    async def fake_batch_verify(*, c2, **kwargs):
        return [{**entry, "s3": 0.8} for entry in c2]

    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)
    monkeypatch.setattr(retrieval, "batch_verify", fake_batch_verify)

    result = asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "query",
                    "table_name": "query_table",
                    "text_blob": "query",
                    "type_multiset": [],
                    "table_vector": [0.1, 0.2],
                    "columns": [{"name": "join_key", "dtype": "str"}],
                },
                "candidate_profiles": {
                    "lexical": {"table_id": "lexical", "text_blob": "l", "type_multiset": []},
                    "semantic_1": {"table_id": "semantic_1", "text_blob": "s1", "type_multiset": []},
                    "semantic_2": {"table_id": "semantic_2", "text_blob": "s2", "type_multiset": []},
                },
                "plan": {
                    "column_recall_enabled": True,
                    "column_recall_top_k": 10,
                    "column_recall_add_k": 1,
                },
            }
        )
    )

    assert result["c2_vec"] == ["lexical", "semantic_1"]


def test_retrieval_run_adds_column_recall_candidates_after_l2(monkeypatch) -> None:
    from adacascade.agents import retrieval

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "lexical", "s1": 0.8}],
    )
    monkeypatch.setattr(
        retrieval,
        "recall_tables_by_columns",
        lambda **kwargs: asyncio.sleep(
            0, result=[{"table_id": "semantic", "s1": 0.35, "s2": 0.35}]
        ),
    )

    async def fake_search_and_build_c2(*args, **kwargs):
        return [{"table_id": "lexical", "s1": 0.8, "s2": 0.9}], False

    async def fake_batch_verify(*, c2, **kwargs):
        return [{**entry, "s3": 0.8} for entry in c2]

    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)
    monkeypatch.setattr(retrieval, "batch_verify", fake_batch_verify)

    result = asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "query",
                    "table_name": "query_table",
                    "text_blob": "query",
                    "type_multiset": [],
                    "table_vector": [0.1, 0.2],
                    "columns": [{"name": "join_key", "dtype": "str"}],
                },
                "candidate_profiles": {
                    "lexical": {"table_id": "lexical", "text_blob": "l", "type_multiset": []},
                    "semantic": {"table_id": "semantic", "text_blob": "s", "type_multiset": []},
                },
                "plan": {"column_recall_enabled": True, "column_recall_top_k": 10},
            }
        )
    )

    assert result["c2_vec"] == ["lexical", "semantic"]


def test_recall_tables_by_samples_filters_low_information_tokens() -> None:
    from adacascade.agents import retrieval

    result = retrieval.recall_tables_by_samples(
        query_profile={
            "columns": [
                {"name": "join_key", "sample_values": ["0", "0.0", "Alpha", "Beta"]}
            ]
        },
        candidate_profiles={
            "kept": {
                "table_id": "kept",
                "columns": [{"name": "id", "sample_values": ["alpha", "gamma"]}],
            },
            "ignored": {
                "table_id": "ignored",
                "columns": [{"name": "id", "sample_values": ["0", "0.0"]}],
            },
        },
        min_overlap=1,
    )

    assert result == [{"table_id": "kept", "s1": pytest.approx(1 / 3)}]


def test_retrieval_run_adds_sample_recall_candidates_after_l2(monkeypatch) -> None:
    from adacascade.agents import retrieval

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "lexical", "s1": 0.8}],
    )

    async def fake_search_and_build_c2(*args, **kwargs):
        return [{"table_id": "lexical", "s1": 0.8, "s2": 0.9}], False

    async def fake_batch_verify(*, c2, **kwargs):
        return [{**entry, "s3": 0.8} for entry in c2]

    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)
    monkeypatch.setattr(retrieval, "batch_verify", fake_batch_verify)

    result = asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "query",
                    "table_name": "query_table",
                    "text_blob": "query",
                    "type_multiset": [],
                    "table_vector": [0.1, 0.2],
                    "columns": [{"name": "join_key", "sample_values": ["Alpha", "0"]}],
                },
                "candidate_profiles": {
                    "lexical": {
                        "table_id": "lexical",
                        "text_blob": "l",
                        "type_multiset": [],
                        "columns": [],
                    },
                    "sample": {
                        "table_id": "sample",
                        "text_blob": "s",
                        "type_multiset": [],
                        "columns": [{"name": "id", "sample_values": ["alpha"]}],
                    },
                },
                "plan": {
                    "sample_recall_enabled": True,
                    "sample_recall_add_k": 1,
                    "sample_recall_min_overlap": 1,
                },
            }
        )
    )

    assert set(result["c2_vec"]) == {"lexical", "sample"}


def test_retrieval_run_passes_source_system_to_layer2(monkeypatch) -> None:
    from adacascade.agents import retrieval

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        retrieval,
        "build_c1",
        lambda *args, **kwargs: [{"table_id": "candidate", "s1": 0.8}],
    )

    async def fake_search_and_build_c2(*args, **kwargs):
        seen["source_system"] = kwargs.get("source_system")
        return [], False

    monkeypatch.setattr(retrieval, "search_and_build_c2", fake_search_and_build_c2)

    result = asyncio.run(
        retrieval.run(
            {
                "task_id": "",
                "tenant_id": "benchmark",
                "corpus": "join",
                "query_profile": {
                    "table_id": "query",
                    "text_blob": "query",
                    "type_multiset": [],
                    "table_vector": [0.1, 0.2],
                },
                "candidate_profiles": {
                    "candidate": {
                        "table_id": "candidate",
                        "text_blob": "candidate",
                        "type_multiset": [],
                    }
                },
                "plan": {},
            }
        )
    )

    assert seen == {"source_system": "retrieval|join"}
    assert result["ranking"] == []



def test_search_and_build_c2_filters_qdrant_by_source_system(monkeypatch) -> None:
    from adacascade.agents.retrieval.layer2 import search_and_build_c2

    seen: dict[str, object] = {}

    class FakeQdrant:
        async def search_tables(self, **kwargs):
            seen.update(kwargs)
            return [{"table_id": "A", "score": 0.9}]

    monkeypatch.setattr(
        "adacascade.indexing.registry.get_qdrant", lambda: FakeQdrant()
    )

    result, degraded = asyncio.run(
        search_and_build_c2(
            c1=[{"table_id": "A", "s1": 0.8}],
            query_vector=[0.1, 0.2],
            tenant_id="benchmark",
            theta_2=0.55,
            k_2=40,
            source_system="retrieval|join",
        )
    )

    assert seen["source_system"] == "retrieval|join"
    assert result[0]["table_id"] == "A"
    assert degraded is True



def test_search_and_build_c2_marks_degraded_before_fallback(monkeypatch) -> None:
    from adacascade.agents.retrieval.layer2 import search_and_build_c2

    class FakeQdrant:
        async def search_tables(self, **kwargs):
            return [{"table_id": "A", "score": 0.9}]

    monkeypatch.setattr(
        "adacascade.indexing.registry.get_qdrant", lambda: FakeQdrant()
    )

    result, degraded = asyncio.run(
        search_and_build_c2(
            c1=[
                {"table_id": "A", "s1": 0.8},
                {"table_id": "B", "s1": 0.7},
                {"table_id": "C", "s1": 0.6},
                {"table_id": "D", "s1": 0.5},
            ],
            query_vector=[0.1, 0.2],
            tenant_id="benchmark",
            theta_2=0.55,
            k_2=40,
        )
    )

    assert len(result) == 3
    assert degraded is True



def test_qdrant_column_search_filters_source_system() -> None:
    from adacascade.indexing.qdrant_client import AdacQdrantClient

    seen: dict[str, object] = {}

    class FakeClient:
        async def query_points(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(points=[])

    client = AdacQdrantClient(FakeClient())

    asyncio.run(
        client.search_columns(
            vector=[0.1, 0.2],
            tenant_id="benchmark",
            top_k=40,
            source_system="retrieval|join",
        )
    )

    conditions = seen["query_filter"].must
    assert any(
        condition.key == "source_system"
        and condition.match.value == "retrieval|join"
        for condition in conditions
    )


def test_qdrant_table_search_filters_source_system() -> None:
    from adacascade.indexing.qdrant_client import AdacQdrantClient

    seen: dict[str, object] = {}

    class FakeClient:
        async def query_points(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(points=[])

    client = AdacQdrantClient(FakeClient())

    asyncio.run(
        client.search_tables(
            vector=[0.1, 0.2],
            tenant_id="benchmark",
            top_k=40,
            source_system="retrieval|join",
        )
    )

    conditions = seen["query_filter"].must
    assert any(
        condition.key == "source_system"
        and condition.match.value == "retrieval|join"
        for condition in conditions
    )



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


def test_c2_fallback_when_empty_stays_within_c1() -> None:
    from adacascade.agents.retrieval.layer2 import intersect_c2

    c1 = [{"table_id": "A", "s1": 0.8}]

    result = intersect_c2(c1, {"B"}, {"B": 0.9}, theta_2=0.55, fallback=True)

    assert result == [{"table_id": "A", "s1": 0.8, "s2": 0.0}]


def test_l3_prompt_includes_required_json_shape() -> None:
    from adacascade.agents.retrieval.layer3 import _build_batch_prompt

    messages = _build_batch_prompt(
        "query",
        [{"name": "id", "dtype": "int"}],
        [{"table_name": "candidate", "columns": [{"name": "id", "dtype": "int"}]}],
        "JOIN",
        0,
    )

    prompt = "\n".join(message["content"] for message in messages)

    assert '"scores"' in prompt
    assert '"candidate_idx"' in prompt
    assert '"score"' in prompt
    assert '"reason"' in prompt
    assert "candidate_idx must match the numbered candidate" in prompt
    assert "reason must be under 160 characters" in prompt
    assert "reason must be under 60 characters" not in prompt


def test_l3_batch_invalid_schema_raises() -> None:
    """Mock LLM returning invalid JSON must raise via Pydantic, not silently pass."""
    from adacascade.llm_schemas import L3BatchResult
    import pytest

    bad_json = '{"scores": [{"candidate_idx": 1, "score": 1.5, "reason": "x"}]}'
    with pytest.raises(Exception):  # score > 1.0 violates Field(le=1.0)
        L3BatchResult.model_validate_json(bad_json)


def test_l3_batch_accepts_concise_but_useful_reason() -> None:
    from adacascade.llm_schemas import L3BatchResult

    result = L3BatchResult.model_validate_json(
        '{"scores":[{"candidate_idx":1,"score":0.95,"reason":"High overlap on herd_id, livestock_program, animal_care_plan, breed_name"}]}'
    )

    assert result.scores[0].score == 0.95


def test_l3_batch_uses_opt_in_cache(monkeypatch) -> None:
    from types import SimpleNamespace

    from adacascade.agents.retrieval import layer3

    calls = 0

    def fake_chat(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"scores":[{"candidate_idx":1,"score":0.9,'
                            '"reason":"same entity"}]}'
                        )
                    )
                )
            ]
        )

    monkeypatch.setattr(layer3, "chat", fake_chat)
    layer3.clear_cache()
    kwargs = {
        "c2": [
            {
                "table_id": "A",
                "table_name": "candidate",
                "columns": [{"name": "id", "dtype": "int"}],
                "s1": 0.7,
                "s2": 0.8,
            }
        ],
        "query_name": "query",
        "query_cols": [{"name": "id", "dtype": "int"}],
        "task_type": "JOIN",
        "theta_3": 0.5,
        "use_cache": True,
    }

    first = asyncio.run(layer3.batch_verify(**kwargs))
    second = asyncio.run(layer3.batch_verify(**kwargs))

    assert calls == 1
    assert first == second


def test_l3_batch_missing_idx_scores_zero() -> None:
    """Candidates with no LLM score entry get S3=0.0 and are excluded from C3."""
    from adacascade.agents.retrieval.layer3 import _merge_scores

    c2 = [{"table_id": "A"}, {"table_id": "B"}]
    llm_scores = {1: 0.8}  # only idx=1 (A) scored
    result = _merge_scores(c2, llm_scores, theta_3=0.5)
    assert len(result) == 1
    assert result[0]["table_id"] == "A"
    assert result[0]["s3"] == pytest.approx(0.8)


def test_l3_retries_once_when_llm_returns_missing_scores(monkeypatch) -> None:
    from adacascade.agents.retrieval import layer3

    responses = iter(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"scores":[{"candidate_idx":1,"score":0.9,'
                                '"reason":"same entity"}]}'
                            )
                        )
                    )
                ]
            ),
        ]
    )
    calls = 0

    call_kwargs = []

    def fake_chat(*_args, **kwargs):
        nonlocal calls
        calls += 1
        call_kwargs.append(kwargs)
        return next(responses)

    monkeypatch.setattr(layer3, "chat", fake_chat)

    result = asyncio.run(
        layer3.batch_verify(
            c2=[
                {
                    "table_id": "A",
                    "table_name": "candidate",
                    "columns": [{"name": "id", "dtype": "int"}],
                    "s1": 0.7,
                    "s2": 0.8,
                }
            ],
            query_name="query",
            query_cols=[{"name": "id", "dtype": "int"}],
            task_type="JOIN",
            theta_3=0.5,
        )
    )

    assert calls == 2
    assert all(kwargs["max_tokens"] == 1024 for kwargs in call_kwargs)
    assert result[0]["table_id"] == "A"
    assert result[0]["s3"] == pytest.approx(0.9)


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
