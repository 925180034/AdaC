from __future__ import annotations


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
