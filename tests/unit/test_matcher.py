from __future__ import annotations

import asyncio
import time

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


def test_matcher_verification_uses_opt_in_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents.matcher import llm_verify
    from adacascade.llm_schemas import MatchResult

    calls = 0

    def fake_verify_pair(*args: object, **kwargs: object) -> MatchResult:
        nonlocal calls
        calls += 1
        return MatchResult(reasoning="same", score=0.9, is_equivalent=True)

    monkeypatch.setattr(llm_verify, "verify_pair", fake_verify_pair)
    llm_verify.clear_cache()
    pairs = [{"src_idx": 0, "tgt_idx": 0, "src_col_id": "src", "tgt_col_id": "tgt"}]
    source_cols = [_numeric_col("name", "src")]
    target_cols = [_numeric_col("name", "tgt")]

    first = llm_verify.verify_pairs(
        pairs, source_cols, target_cols, "SMD", use_cache=True
    )
    second = llm_verify.verify_pairs(
        pairs, source_cols, target_cols, "SMD", use_cache=True
    )

    assert calls == 1
    assert first[0]["llm_result"] == second[0]["llm_result"]
    assert first[0]["cache_key"] == second[0]["cache_key"]
    assert first[0]["cache_hit"] is False
    assert second[0]["cache_hit"] is True


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


@pytest.mark.anyio
async def test_matcher_llm_verification_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    async def slow_verify_pairs_async(
        *args: object, **kwargs: object
    ) -> list[dict[str, object]]:
        await asyncio.to_thread(time.sleep, 0.05)
        return [
            {
                "src_idx": 0,
                "tgt_idx": 0,
                "src_col_id": "src",
                "tgt_col_id": "tgt",
                "llm_result": MatchResult(
                    reasoning="same", score=0.9, is_equivalent=True
                ),
            }
        ]

    monkeypatch.setattr(
        matcher.llm_verify, "verify_pairs_async", slow_verify_pairs_async
    )

    task = asyncio.create_task(
        matcher.run(
            {
                "task_id": "",
                "tenant_id": "default",
                "task_type": "MATCH_ONLY",
                "query_profile": {
                    "table_id": "source",
                    "columns": [_numeric_col("name", "src")],
                },
                "target_profile": {
                    "table_id": "target",
                    "columns": [_numeric_col("name", "tgt")],
                },
                "plan": {},
                "status": "RUNNING",
                "degraded": False,
            }
        )
    )
    await asyncio.sleep(0.01)

    assert not task.done()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.anyio
async def test_matcher_run_returns_similarity_pairs_for_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    async def fake_verify_pairs_async(
        pairs: list[dict[str, object]], *args: object, **kwargs: object
    ) -> list[dict[str, object]]:
        return [
            {
                "src_idx": 0,
                "tgt_idx": 0,
                "src_col_id": "src",
                "tgt_col_id": "tgt",
                "llm_result": MatchResult(
                    reasoning="same", score=0.9, is_equivalent=True
                ),
            }
        ]

    monkeypatch.setattr(
        matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async
    )

    result = await matcher.run(
        {
            "task_id": "",
            "tenant_id": "default",
            "task_type": "MATCH_ONLY",
            "query_profile": {
                "table_id": "source",
                "columns": [_numeric_col("name", "src")],
            },
            "target_profile": {
                "table_id": "target",
                "columns": [_numeric_col("name", "tgt")],
            },
            "plan": {},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert len(result["similarity_pairs"]) == 1
    assert result["similarity_pairs"][0]["src_col_id"] == "src"


@pytest.mark.anyio
async def test_matcher_run_returns_stage_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    async def fake_verify_pairs_async(
        pairs: list[dict[str, object]], *args: object, **kwargs: object
    ) -> list[dict[str, object]]:
        return [
            {
                "src_idx": 0,
                "tgt_idx": 0,
                "src_col_id": "src",
                "tgt_col_id": "tgt",
                "llm_result": MatchResult(
                    reasoning="same", score=0.9, is_equivalent=True
                ),
            }
        ]

    monkeypatch.setattr(
        matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async
    )

    result = await matcher.run(
        {
            "task_id": "",
            "tenant_id": "default",
            "task_type": "MATCH_ONLY",
            "query_profile": {
                "table_id": "source",
                "columns": [_numeric_col("name", "src")],
            },
            "target_profile": {
                "table_id": "target",
                "columns": [_numeric_col("name", "tgt")],
            },
            "plan": {},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert set(result["stage_timings_ms"]) == {
        "candidate_filtering",
        "llm_verification",
        "decision",
    }
    assert all(value >= 0 for value in result["stage_timings_ms"].values())


@pytest.mark.anyio
async def test_matcher_run_aggregates_llm_verification_metrics_across_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    seen_kwargs: dict[str, object] = {}
    call_index = 0

    async def fake_verify_pairs_async(
        pairs: list[dict[str, object]], *_args: object, **kwargs: object
    ) -> list[dict[str, object]]:
        nonlocal call_index
        seen_kwargs.update(kwargs)
        if call_index == 0:
            verified = [
                {
                    **pairs[0],
                    "llm_result": MatchResult(reasoning="same", score=0.9, is_equivalent=True),
                    "cache_hit": False,
                    "cache_source": "miss",
                    "llm_latency_ms": 10.0,
                },
                {
                    **pairs[1],
                    "llm_result": MatchResult(reasoning="same", score=0.8, is_equivalent=True),
                    "cache_hit": False,
                    "cache_source": "miss",
                    "llm_latency_ms": 20.0,
                },
            ]
        else:
            verified = [
                {
                    **pairs[0],
                    "llm_result": MatchResult(reasoning="same", score=0.7, is_equivalent=True),
                    "cache_hit": False,
                    "cache_source": "miss",
                    "llm_latency_ms": 30.0,
                },
                {
                    **pairs[1],
                    "llm_result": MatchResult(reasoning="same", score=0.6, is_equivalent=True),
                    "cache_hit": True,
                    "cache_source": "sqlite",
                    "llm_latency_ms": 0.0,
                },
            ]
        call_index += 1
        return verified

    def fake_filter_cpi(_source_cols, _target_cols, _scenario, theta_cand=None):
        return [
            {"src_idx": 0, "tgt_idx": 0, "src_col_id": "src_a", "tgt_col_id": "tgt_a", "m_score": 0.9},
            {"src_idx": 1, "tgt_idx": 1, "src_col_id": "src_b", "tgt_col_id": "tgt_b", "m_score": 0.8},
        ]

    monkeypatch.setattr(matcher, "filter_cpi", fake_filter_cpi)
    monkeypatch.setattr(matcher, "truncate_per_source", lambda pairs: pairs)
    monkeypatch.setattr(matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async)

    result = await matcher.run(
        {
            "task_id": "",
            "tenant_id": "default",
            "task_type": "INTEGRATE",
            "query_profile": {
                "table_id": "source",
                "columns": [_numeric_col("name_a", "src_a"), _numeric_col("name_b", "src_b")],
            },
            "candidate_profiles": {
                "target_1": {
                    "table_id": "target_1",
                    "columns": [_numeric_col("name_a", "tgt_a"), _numeric_col("name_b", "tgt_b")],
                },
                "target_2": {
                    "table_id": "target_2",
                    "columns": [_numeric_col("name_a", "tgt_a"), _numeric_col("name_b", "tgt_b")],
                },
            },
            "ranking": [{"table_id": "target_1"}, {"table_id": "target_2"}],
            "plan": {"matcher_llm_concurrency": 12, "llm_cache_enabled": True},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    assert call_index == 2
    assert seen_kwargs["concurrency"] == 12
    assert seen_kwargs["use_cache"] is True
    assert result["matcher_metrics"] == {
        "verified_pair_count": 4,
        "cache_hit_count": 1,
        "memory_cache_hit_count": 0,
        "sqlite_cache_hit_count": 1,
        "cache_miss_count": 3,
        "llm_call_count": 3,
        "matcher_verify_ms": pytest.approx(result["stage_timings_ms"]["llm_verification"]),
        "llm_verify_p50_ms": 20.0,
        "llm_verify_p95_ms": 30.0,
    }


@pytest.mark.anyio
async def test_matcher_emits_one_ordered_lifecycle_for_multiple_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    events: list[dict[str, object]] = []

    async def fake_emit_task_event(_task_id: str, payload: dict[str, object]) -> None:
        events.append(payload)

    async def fake_verify_pairs_async(
        pairs: list[dict[str, object]], *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        return [
            {
                **pair,
                "llm_result": MatchResult(reasoning="same", score=0.9, is_equivalent=True),
            }
            for pair in pairs
        ]

    def fake_filter_cpi(_source_cols, _target_cols, _scenario, theta_cand=None):
        return [
            {"src_idx": 0, "tgt_idx": 0, "src_col_id": "src", "tgt_col_id": "tgt", "m_score": 0.9}
        ]

    monkeypatch.setattr(matcher, "emit_task_event", fake_emit_task_event)
    monkeypatch.setattr(matcher, "filter_cpi", fake_filter_cpi)
    monkeypatch.setattr(matcher, "truncate_per_source", lambda pairs: pairs)
    monkeypatch.setattr(matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async)
    monkeypatch.setattr(matcher, "save_pkl", lambda *_args: "/tmp/sim.pkl")

    await matcher.run(
        {
            "task_id": "task-multi-target",
            "tenant_id": "default",
            "task_type": "INTEGRATE",
            "query_profile": {
                "table_id": "source",
                "columns": [_numeric_col("name", "src")],
            },
            "candidate_profiles": {
                "target_1": {
                    "table_id": "target_1",
                    "columns": [_numeric_col("name", "tgt")],
                },
                "target_2": {
                    "table_id": "target_2",
                    "columns": [_numeric_col("name", "tgt")],
                },
            },
            "ranking": [{"table_id": "target_1"}, {"table_id": "target_2"}],
            "plan": {},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    lifecycle = [
        (event["layer"], event["type"])
        for event in events
        if event.get("agent") == "Matcher"
    ]
    assert lifecycle == [
        ("filtering", "agent_started"),
        ("filtering", "agent_completed"),
        ("LLM", "agent_started"),
        ("LLM", "agent_completed"),
        ("decision", "agent_started"),
        ("decision", "agent_completed"),
    ]


@pytest.mark.anyio
async def test_matcher_zero_processed_targets_llm_completion_includes_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from adacascade.agents import matcher

    events: list[dict[str, object]] = []

    async def fake_emit_task_event(_task_id: str, payload: dict[str, object]) -> None:
        events.append(payload)

    monkeypatch.setattr(matcher, "emit_task_event", fake_emit_task_event)
    monkeypatch.setattr(matcher, "save_pkl", lambda *_args: "/tmp/sim.pkl")

    result = await matcher.run(
        {
            "task_id": "task-empty",
            "tenant_id": "default",
            "task_type": "MATCH_ONLY",
            "query_profile": {
                "table_id": "source",
                "columns": [_numeric_col("name", "src")],
            },
            "plan": {},
            "status": "RUNNING",
            "degraded": False,
        }
    )

    llm_completion = next(
        event
        for event in events
        if event["type"] == "agent_completed" and event["layer"] == "LLM"
    )
    assert llm_completion["metrics"] == result["matcher_metrics"]
