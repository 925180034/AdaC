"""Matcher LLM verification with JSON Schema constrained output."""

from __future__ import annotations

from typing import Any

from adacascade import llm_client
from adacascade.llm_schemas import MatchResult, json_schema_format
from adacascade.agents.matcher.mixed import Scenario


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
    resp = llm_client.chat(
        build_prompt(src_col, tgt_col, component_scores, scenario),
        response_format=json_schema_format(MatchResult),
        temperature=0.0,
        enable_thinking=False,
    )
    content = resp.choices[0].message.content or ""
    return parse_match_result(content)


def verify_pairs(
    pairs: list[dict[str, Any]],
    source_cols: list[dict[str, Any]],
    target_cols: list[dict[str, Any]],
    scenario: Scenario,
) -> list[dict[str, Any]]:
    """Verify candidate pairs sequentially and attach LLM decisions."""
    results: list[dict[str, Any]] = []
    for pair in pairs:
        src_col = source_cols[int(pair["src_idx"])]
        tgt_col = target_cols[int(pair["tgt_idx"])]
        scores = {
            "sim_name": float(pair.get("sim_name", 0.0)),
            "sim_type": float(pair.get("sim_type", 0.0)),
            "sim_stat": float(pair.get("sim_stat", 0.0)),
            "m_score": float(pair.get("m_score", 0.0)),
        }
        decision = verify_pair(src_col, tgt_col, scores, scenario)
        results.append({**pair, "llm_result": decision})
    return results
