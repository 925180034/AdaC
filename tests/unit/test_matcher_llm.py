"""Matcher LLM verification tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from adacascade.agents.matcher.llm_verify import build_prompt, parse_match_result
from adacascade.llm_runtime import LlmRequestConfig


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


def test_verify_pairs_reports_cache_hit_miss_and_latency(
    monkeypatch: pytest.MonkeyPatch,
    source_col: dict[str, object],
    target_col: dict[str, object],
) -> None:
    from adacascade.agents.matcher import llm_verify
    from adacascade.llm_schemas import MatchResult

    calls = 0

    def fake_verify_pair(*_args: object, **_kwargs: object) -> MatchResult:
        nonlocal calls
        calls += 1
        return MatchResult(reasoning="same", score=0.9, is_equivalent=True)

    monkeypatch.setattr(llm_verify, "verify_pair", fake_verify_pair)
    llm_verify.clear_cache()
    pairs = [{"src_idx": 0, "tgt_idx": 0, "src_col_id": "s1", "tgt_col_id": "t1"}]

    first = llm_verify.verify_pairs(pairs, [source_col], [target_col], "SMD", use_cache=True)
    second = llm_verify.verify_pairs(pairs, [source_col], [target_col], "SMD", use_cache=True)

    assert calls == 1
    assert first[0]["cache_hit"] is False
    assert first[0]["cache_key"] == second[0]["cache_key"]
    assert first[0]["llm_latency_ms"] >= 0
    assert second[0]["cache_hit"] is True
    assert second[0]["llm_latency_ms"] == 0.0


def test_verify_pairs_does_not_reuse_cache_across_runtime_configs(
    monkeypatch: pytest.MonkeyPatch,
    source_col: dict[str, object],
    target_col: dict[str, object],
) -> None:
    from adacascade.agents.matcher import llm_verify
    from adacascade.llm_schemas import MatchResult

    runtime_configs = [
        LlmRequestConfig(
            backend="local",
            base_url="http://localhost:8000/v1",
            api_key="local-secret",
            model="local-model",
            timeout=30,
        ),
        LlmRequestConfig(
            backend="api",
            base_url="https://llm.example.test/v1",
            api_key="api-secret",
            model="api-model",
            timeout=30,
        ),
    ]
    calls = 0

    def fake_get_request_config() -> LlmRequestConfig:
        return runtime_configs[calls]

    def fake_verify_pair(*_args: object, **_kwargs: object) -> MatchResult:
        nonlocal calls
        calls += 1
        return MatchResult(reasoning=f"runtime-{calls}", score=0.9, is_equivalent=True)

    monkeypatch.setattr(
        llm_verify.llm_runtime, "get_request_config", fake_get_request_config
    )
    monkeypatch.setattr(llm_verify, "verify_pair", fake_verify_pair)
    llm_verify.clear_cache()
    pairs = [{"src_idx": 0, "tgt_idx": 0, "src_col_id": "s1", "tgt_col_id": "t1"}]

    first = llm_verify.verify_pairs(pairs, [source_col], [target_col], "SMD", use_cache=True)
    second = llm_verify.verify_pairs(pairs, [source_col], [target_col], "SMD", use_cache=True)

    assert calls == 2
    assert first[0]["cache_hit"] is False
    assert second[0]["cache_hit"] is False
    assert first[0]["cache_key"] != second[0]["cache_key"]
