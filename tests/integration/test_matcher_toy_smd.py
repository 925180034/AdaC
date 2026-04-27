"""Toy direct Matcher integration for SMD."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from adacascade.llm_schemas import MatchResult
from adacascade.state import IntegrationState


def _col(col_id: str, name: str, dtype: str = "str") -> dict[str, object]:
    return {
        "col_id": col_id,
        "name": name,
        "dtype": dtype,
        "description": name.replace("_", " "),
        "numeric_stats": None,
        "categorical_stats": None,
        "sample_values": [],
    }


def test_matcher_toy_smd() -> None:
    from adacascade.agents import matcher

    state: IntegrationState = {
        "task_id": "toy_matcher_smd",
        "tenant_id": "benchmark",
        "task_type": "MATCH_ONLY",
        "subtask": "UNION",
        "query_profile": {
            "table_id": "source",
            "table_name": "source",
            "columns": [_col("s_name", "patient_id"), _col("s_age", "age", "int")],
        },
        "target_profile": {
            "table_id": "target",
            "table_name": "target",
            "columns": [_col("t_name", "patient_id"), _col("t_age", "age", "int")],
        },
    }

    def fake_verify_pair(
        src_col: dict[str, object],
        tgt_col: dict[str, object],
        component_scores: dict[str, float],
        scenario: str,
    ) -> MatchResult:
        same_name = src_col["name"] == tgt_col["name"]
        return MatchResult(
            reasoning="same name" if same_name else "different name",
            score=0.95 if same_name else 0.1,
            is_equivalent=same_name,
        )

    with patch(
        "adacascade.agents.matcher.llm_verify.verify_pair", side_effect=fake_verify_pair
    ):
        result = asyncio.run(matcher.run(state))

    pairs = {
        (item["source_column"], item["target_column"])
        for item in result["final_mappings"]
    }
    assert ("patient_id", "patient_id") in pairs
    assert ("age", "age") in pairs
