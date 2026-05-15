"""Matcher LLM verification with JSON Schema constrained output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from adacascade import llm_client, llm_runtime
from adacascade.agents.matcher import cache_store
from adacascade.llm_schemas import MatchResult, json_schema_format
from adacascade.agents.matcher.mixed import Scenario

PROMPT_VERSION = "matcher-v1"

_cache: dict[str, MatchResult] = {}


def clear_cache() -> None:
    _cache.clear()


def _memory_put(cache_key: str, decision: MatchResult) -> None:
    _cache[cache_key] = decision


def _stable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable_payload(item) for item in value]
    return value


def _column_payload(col: dict[str, Any]) -> dict[str, Any]:
    return {
        "col_id": col.get("col_id"),
        "name": col.get("name"),
        "dtype": col.get("dtype"),
        "description": col.get("description", ""),
        "sample_values": col.get("sample_values", []),
        "numeric_stats": col.get("numeric_stats"),
        "categorical_stats": col.get("categorical_stats"),
    }


def _cache_key(
    src_col: dict[str, Any],
    tgt_col: dict[str, Any],
    component_scores: dict[str, float],
    scenario: Scenario,
) -> str:
    runtime_config = llm_runtime.get_request_config()
    payload = {
        "prompt_version": PROMPT_VERSION,
        "llm_runtime": {
            "backend": runtime_config.backend,
            "base_url": runtime_config.base_url,
            "model": runtime_config.model,
        },
        "src": _column_payload(src_col),
        "tgt": _column_payload(tgt_col),
        "component_scores": component_scores,
        "scenario": scenario,
    }
    raw = json.dumps(_stable_payload(payload), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _field(col: dict[str, Any], key: str, default: Any = "") -> Any:
    return col.get(key, default)


def _base_column_block(label: str, col: dict[str, Any]) -> str:
    return (
        f"{label}:\n"
        f"- id: {_field(col, 'col_id')}\n"
        f"- name: {_field(col, 'name')}\n"
        f"- dtype: {_field(col, 'dtype')}\n"
        f"- description: {_field(col, 'description', '')}"
    )


def build_prompt(
    src_col: dict[str, Any],
    tgt_col: dict[str, Any],
    component_scores: dict[str, float],
    scenario: Scenario,
) -> list[dict[str, str]]:
    """Build the five-block matcher verification prompt."""
    instance_lines = [
        _base_column_block("Source column", src_col),
        _base_column_block("Target column", tgt_col),
        "Similarity signals:",
        f"- Sim_name: {component_scores.get('sim_name', 0.0):.4f}",
        f"- Sim_type: {component_scores.get('sim_type', 0.0):.4f}",
    ]

    if scenario in ("SSD", "SLD"):
        instance_lines.extend(
            [
                f"- source sample_values: {_field(src_col, 'sample_values', [])}",
                f"- target sample_values: {_field(tgt_col, 'sample_values', [])}",
            ]
        )

    if scenario == "SLD":
        instance_lines.extend(
            [
                f"- source numeric_stats: {_field(src_col, 'numeric_stats', {})}",
                f"- target numeric_stats: {_field(tgt_col, 'numeric_stats', {})}",
                f"- Sim_stat: {component_scores.get('sim_stat', 0.0):.4f}",
                f"- M_mixed: {component_scores.get('m_score', component_scores.get('score', 0.0)):.4f}",
            ]
        )

    guide = {
        "SMD": "Use names, types, and descriptions only. Do not assume value overlap is available.",
        "SSD": "Use names, types, descriptions, and sample values. Prefer semantic equivalence over exact spelling.",
        "SLD": "Use all metadata, samples, and statistics. Treat compatible distributions as strong supporting evidence.",
    }[scenario]

    return [
        {
            "role": "system",
            "content": (
                "You are a schema matching verifier. Decide whether two columns "
                "represent the same real-world attribute."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task: verify one candidate column match for scenario {scenario}. "
                "Return a calibrated confidence score in [0, 1]."
            ),
        },
        {"role": "user", "content": "\n".join(instance_lines)},
        {"role": "user", "content": f"Reasoning guide: {guide}"},
        {
            "role": "user",
            "content": (
                "Output JSON only with fields: reasoning, score, is_equivalent. "
                "Do not include markdown."
            ),
        },
    ]


def parse_match_result(content: str) -> MatchResult:
    """Parse and validate one matcher LLM JSON response."""
    return MatchResult.model_validate_json(content)


def verify_pair(
    src_col: dict[str, Any],
    tgt_col: dict[str, Any],
    component_scores: dict[str, float],
    scenario: Scenario,
) -> MatchResult:
    """Verify a single candidate column pair via the configured LLM."""
    try:
        resp = llm_client.chat(
            build_prompt(src_col, tgt_col, component_scores, scenario),
            response_format=json_schema_format(MatchResult),
            temperature=0.0,
            enable_thinking=False,
        )
        content = resp.choices[0].message.content or ""
        return parse_match_result(content)
    except Exception:
        return MatchResult(
            reasoning="LLM verification failed", score=0.0, is_equivalent=False
        )


def _verify_pair_entry(
    pair: dict[str, Any],
    source_cols: list[dict[str, Any]],
    target_cols: list[dict[str, Any]],
    scenario: Scenario,
    *,
    use_cache: bool = False,
) -> dict[str, Any]:
    """Verify one candidate pair and attach the LLM decision."""
    src_col = source_cols[int(pair["src_idx"])]
    tgt_col = target_cols[int(pair["tgt_idx"])]
    scores = {
        "sim_name": float(pair.get("sim_name", 0.0)),
        "sim_type": float(pair.get("sim_type", 0.0)),
        "sim_stat": float(pair.get("sim_stat", 0.0)),
        "m_score": float(pair.get("m_score", 0.0)),
    }
    runtime_config = llm_runtime.get_request_config()
    cache_key = _cache_key(src_col, tgt_col, scores, scenario)
    cache_source = "disabled"
    latency_ms = 0.0
    decision: MatchResult
    if use_cache and cache_key in _cache:
        decision = _cache[cache_key]
        cache_source = "memory"
    elif use_cache:
        cached_decision = cache_store.get(cache_key)
        if cached_decision is not None:
            decision = cached_decision
            _memory_put(cache_key, decision)
            cache_source = "sqlite"
        else:
            started = time.perf_counter()
            decision = verify_pair(src_col, tgt_col, scores, scenario)
            latency_ms = (time.perf_counter() - started) * 1000
            cache_source = "miss"
            _memory_put(cache_key, decision)
            cache_store.put(
                cache_key,
                runtime_config=runtime_config,
                prompt_version=PROMPT_VERSION,
                scenario=scenario,
                src_col=src_col,
                tgt_col=tgt_col,
                src_payload=_column_payload(src_col),
                tgt_payload=_column_payload(tgt_col),
                component_scores=scores,
                result=decision,
            )
    else:
        started = time.perf_counter()
        decision = verify_pair(src_col, tgt_col, scores, scenario)
        latency_ms = (time.perf_counter() - started) * 1000
    return {
        **pair,
        "llm_result": decision,
        "cache_key": cache_key,
        "cache_hit": cache_source in {"memory", "sqlite"},
        "cache_source": cache_source,
        "llm_latency_ms": latency_ms,
    }


def verify_pairs(
    pairs: list[dict[str, Any]],
    source_cols: list[dict[str, Any]],
    target_cols: list[dict[str, Any]],
    scenario: Scenario,
    *,
    use_cache: bool = False,
) -> list[dict[str, Any]]:
    """Verify candidate pairs sequentially and attach LLM decisions."""
    return [
        _verify_pair_entry(
            pair, source_cols, target_cols, scenario, use_cache=use_cache
        )
        for pair in pairs
    ]


async def verify_pairs_async(
    pairs: list[dict[str, Any]],
    source_cols: list[dict[str, Any]],
    target_cols: list[dict[str, Any]],
    scenario: Scenario,
    concurrency: int = 4,
    *,
    use_cache: bool = False,
) -> list[dict[str, Any]]:
    """Verify candidate pairs concurrently without blocking the event loop."""
    semaphore = asyncio.Semaphore(concurrency)

    async def _run(pair: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.to_thread(
                _verify_pair_entry,
                pair,
                source_cols,
                target_cols,
                scenario,
                use_cache=use_cache,
            )

    return list(await asyncio.gather(*(_run(pair) for pair in pairs)))
