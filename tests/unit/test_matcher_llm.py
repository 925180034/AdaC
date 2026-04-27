"""Matcher LLM verification tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from adacascade.agents.matcher.llm_verify import build_prompt, parse_match_result


@pytest.fixture
def source_col() -> dict[str, object]:
    return {
        "col_id": "s1",
        "name": "patient_id",
        "dtype": "str",
        "description": "Patient identifier",
        "sample_values": ["p1", "p2"],
        "numeric_stats": None,
    }


@pytest.fixture
def target_col() -> dict[str, object]:
    return {
        "col_id": "t1",
        "name": "person_id",
        "dtype": "str",
        "description": "Person identifier",
        "sample_values": ["p3", "p4"],
        "numeric_stats": None,
    }


def test_llm_json_schema() -> None:
    valid = parse_match_result(
        '{"reasoning":"same identifier","score":0.9,"is_equivalent":true}'
    )
    assert valid.score == 0.9
    with pytest.raises(ValidationError):
        parse_match_result(
            '{"reasoning":"bad confidence","score":1.2,"is_equivalent":true}'
        )
    with pytest.raises(ValidationError):
        parse_match_result("not json")


def test_build_prompt_smd_ssd_sld(
    source_col: dict[str, object], target_col: dict[str, object]
) -> None:
    scores = {"sim_name": 0.8, "sim_type": 1.0, "sim_stat": 0.7, "m_score": 0.82}
    smd = "\n".join(
        item["content"] for item in build_prompt(source_col, target_col, scores, "SMD")
    )
    ssd = "\n".join(
        item["content"] for item in build_prompt(source_col, target_col, scores, "SSD")
    )
    sld = "\n".join(
        item["content"] for item in build_prompt(source_col, target_col, scores, "SLD")
    )

    assert "Sim_name: 0.8000" in smd
    assert "Sim_type: 1.0000" in smd
    assert "sample_values" not in smd
    assert "sample_values" in ssd
    assert "Sim_stat: 0.7000" in sld
    assert "M_mixed: 0.8200" in sld
