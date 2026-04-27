"""M3 local degradation behavior tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from adacascade.llm_schemas import MatchResult
from adacascade.state import IntegrationState


def _profile(table_id: str) -> dict[str, object]:
    return {
        "table_id": table_id,
        "table_name": table_id,
        "text_blob": table_id,
        "type_multiset": ["str"],
        "table_vector": [0.1, 0.2],
        "columns": [
            {
                "col_id": f"{table_id}_name",
                "name": "name",
                "dtype": "str",
                "description": "name",
                "numeric_stats": None,
                "categorical_stats": None,
                "sample_values": [],
            }
        ],
    }


@pytest.mark.anyio
async def test_retrieval_qdrant_failure_marks_degraded() -> None:
    from adacascade.agents import retrieval

    state: IntegrationState = {
        "task_id": "degraded-retrieval",
        "tenant_id": "default",
        "task_type": "DISCOVER_ONLY",
        "subtask": "JOIN",
        "query_profile": _profile("query"),
        "candidate_profiles": {"target": _profile("target")},
        "plan": {"theta_1": 0.0, "theta_3": 0.5, "k_1": 10},
    }
    with (
        patch(
            "adacascade.agents.retrieval.build_c1",
            return_value=[{"table_id": "target", "s1": 0.8}],
        ),
        patch(
            "adacascade.agents.retrieval.search_and_build_c2",
            new=AsyncMock(side_effect=RuntimeError("qdrant down")),
        ),
        patch(
            "adacascade.agents.retrieval.batch_verify", new=AsyncMock(return_value=[])
        ),
    ):
        result = await retrieval.run(state)

    assert result["degraded"] is True
    assert result["c2_vec"] == ["target"]
    assert result["ranking"] == []


def test_matcher_llm_failure_returns_negative_result() -> None:
    from adacascade.agents.matcher.llm_verify import verify_pair

    with patch(
        "adacascade.agents.matcher.llm_verify.llm_client.chat",
        side_effect=RuntimeError("llm down"),
    ):
        result = verify_pair(
            {"col_id": "s", "name": "name", "dtype": "str"},
            {"col_id": "t", "name": "name", "dtype": "str"},
            {"sim_name": 1.0, "sim_type": 1.0, "m_score": 1.0},
            "SMD",
        )

    assert isinstance(result, MatchResult)
    assert result.score == 0.0
    assert result.is_equivalent is False
