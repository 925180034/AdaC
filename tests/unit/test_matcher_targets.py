"""Matcher target selection tests."""

from __future__ import annotations

from adacascade.agents.matcher import _targets
from adacascade.state import IntegrationState


def test_integrate_empty_ranking_does_not_match_all_candidates() -> None:
    state: IntegrationState = {
        "task_type": "INTEGRATE",
        "ranking": [],
        "candidate_profiles": {
            "candidate-a": {"table_id": "candidate-a", "columns": []},
            "candidate-b": {"table_id": "candidate-b", "columns": []},
        },
    }

    assert _targets(state) == []


def test_integrate_uses_ranked_candidates_only() -> None:
    candidate_a = {"table_id": "candidate-a", "columns": []}
    candidate_b = {"table_id": "candidate-b", "columns": []}
    state: IntegrationState = {
        "task_type": "INTEGRATE",
        "ranking": [{"table_id": "candidate-b"}],
        "candidate_profiles": {
            "candidate-a": candidate_a,
            "candidate-b": candidate_b,
        },
    }

    assert _targets(state) == [candidate_b]


def test_match_only_uses_target_profile_without_ranking() -> None:
    target = {"table_id": "target", "columns": []}
    state: IntegrationState = {
        "task_type": "MATCH_ONLY",
        "ranking": [],
        "target_profile": target,
        "candidate_profiles": {
            "candidate-a": {"table_id": "candidate-a", "columns": []},
        },
    }

    assert _targets(state) == [target]
