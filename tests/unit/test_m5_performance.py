from __future__ import annotations


import asyncio
import time
from types import SimpleNamespace


def test_matcher_targets_are_limited_by_plan_top_k() -> None:
    from adacascade.agents import matcher

    state = {
        "task_type": "INTEGRATE",
        "ranking": [
            {"table_id": "t1", "score": 0.9},
            {"table_id": "t2", "score": 0.8},
            {"table_id": "t3", "score": 0.7},
        ],
        "candidate_profiles": {
            "t1": {"table_id": "t1", "columns": []},
            "t2": {"table_id": "t2", "columns": []},
            "t3": {"table_id": "t3", "columns": []},
        },
        "plan": {"matcher_top_k": 2},
    }

    assert [target["table_id"] for target in matcher._targets(state)] == ["t1", "t2"]


def test_retrieval_l3_respects_concurrency_limit(monkeypatch) -> None:
    from adacascade.agents.retrieval import layer3

    active = 0
    max_active = 0

    def fake_chat(*_args, **_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.02)
        active -= 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"scores":[{"candidate_idx":1,"score":0.9,"reason":"same"}]}'
                    )
                )
            ]
        )

    monkeypatch.setattr(layer3, "chat", fake_chat)

    result = asyncio.run(
        layer3.batch_verify(
            c2=[
                {
                    "table_id": f"t{i}",
                    "table_name": f"table {i}",
                    "columns": [{"name": "id", "dtype": "int"}],
                    "s1": 0.8,
                    "s2": 0.8,
                }
                for i in range(6)
            ],
            query_name="query",
            query_cols=[{"name": "id", "dtype": "int"}],
            task_type="JOIN",
            theta_3=0.5,
            batch_size=1,
            concurrency=2,
        )
    )

    assert max_active == 2
    assert [item["table_id"] for item in result] == ["t0", "t1", "t2", "t3", "t4", "t5"]


def test_matcher_run_passes_plan_thresholds_to_filter_and_decision(monkeypatch) -> None:
    from adacascade.agents import matcher
    from adacascade.llm_schemas import MatchResult

    seen_theta_cand = None
    seen_theta_match = []

    def fake_filter_cpi(_source_cols, _target_cols, _scenario, theta_cand=None):
        nonlocal seen_theta_cand
        seen_theta_cand = theta_cand
        return [{"src_idx": 0, "tgt_idx": 0, "src_col_id": "src", "tgt_col_id": "tgt", "m_score": 0.9}]

    async def fake_verify_pairs_async(pairs, *_args, **_kwargs):
        return [{**pairs[0], "llm_result": MatchResult(reasoning="same", score=0.6, is_equivalent=True)}]

    def fake_decide(_score, theta_match=None):
        seen_theta_match.append(theta_match)
        return True

    monkeypatch.setattr(matcher, "filter_cpi", fake_filter_cpi)
    monkeypatch.setattr(matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async)
    monkeypatch.setattr(matcher, "decide", fake_decide)

    asyncio.run(
        matcher.run(
            {
                "task_id": "",
                "tenant_id": "default",
                "task_type": "MATCH_ONLY",
                "query_profile": {
                    "table_id": "source",
                    "columns": [{"col_id": "src", "name": "name", "dtype": "string"}],
                },
                "target_profile": {
                    "table_id": "target",
                    "columns": [{"col_id": "tgt", "name": "name", "dtype": "string"}],
                },
                "plan": {"theta_cand": 0.25, "theta_match": 0.55},
                "status": "RUNNING",
                "degraded": False,
            }
        )
    )

    assert seen_theta_cand == 0.25
    assert seen_theta_match == [0.55]


def test_matcher_run_passes_plan_concurrency_to_llm_verification(monkeypatch) -> None:
    from adacascade.agents import matcher

    seen_concurrency = None

    async def fake_verify_pairs_async(*_args, **kwargs):
        nonlocal seen_concurrency
        seen_concurrency = kwargs["concurrency"]
        return []

    monkeypatch.setattr(matcher.llm_verify, "verify_pairs_async", fake_verify_pairs_async)

    asyncio.run(
        matcher.run(
            {
                "task_id": "",
                "tenant_id": "default",
                "task_type": "MATCH_ONLY",
                "query_profile": {
                    "table_id": "source",
                    "columns": [{"col_id": "src", "name": "name", "dtype": "string"}],
                },
                "target_profile": {
                    "table_id": "target",
                    "columns": [{"col_id": "tgt", "name": "name", "dtype": "string"}],
                },
                "plan": {"llm_concurrency": 24},
                "status": "RUNNING",
                "degraded": False,
            }
        )
    )

    assert seen_concurrency == 24
