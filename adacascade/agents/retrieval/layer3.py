"""TLCF Layer 3 — LLM batch verification of candidates.

Algorithm Spec §3.4. Batches C₂ into chunks of ≤10 and calls LLM in parallel.
Returns C₃ = {Tc ∈ C₂ | S₃ > θ₃}.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

import structlog

from adacascade.llm_client import chat
from adacascade.llm_schemas import L3BatchResult, json_schema_format

log = structlog.get_logger(__name__)

_BATCH_SIZE = 10  # from configs, single LLM call max candidates


def _build_batch_prompt(
    query_name: str,
    query_cols: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    task_type: Literal["JOIN", "UNION"],
    offset: int,
) -> list[dict[str, str]]:
    """Build messages for one batch (up to _BATCH_SIZE candidates).

    Args:
        query_name: Name of the query table.
        query_cols: Query columns as [{name, dtype}].
        candidates: Candidate entries for this batch.
        task_type: JOIN or UNION task type.
        offset: Global index offset for this batch.

    Returns:
        OpenAI-format message list for the LLM call.
    """
    col_repr = ", ".join(f"{c['name']}:{c['dtype']}" for c in query_cols[:20])
    cand_lines_parts = []
    for i, candidate in enumerate(candidates):
        columns = candidate.get("columns", [])[:10]
        columns_repr = ", ".join(
            f"{column['name']}:{column['dtype']}" for column in columns
        )
        cand_lines_parts.append(
            f"({offset + i + 1}) name: {candidate['table_name']}, "
            f"columns: [{columns_repr}]"
        )
    cand_lines = "\n".join(cand_lines_parts)
    return [
        {
            "role": "system",
            "content": (
                "You are a data integration expert. Given a query table and several "
                "candidate tables, score each candidate's compatibility.\n\n"
                f"Task type: {task_type}\n"
                "- JOIN: candidate must share a joinable column (high value overlap)\n"
                "- UNION: candidate must describe the same entity type (compatible schema)"
            ),
        },
        {
            "role": "user",
            "content": (
                f"[Query Table]\nname: {query_name}\ncolumns: [{col_repr}]\n\n"
                f"[Candidates]\n{cand_lines}\n\n"
                "[Instruction]\nFor each candidate, output compatibility score in [0,1].\n"
                "Output JSON only."
            ),
        },
    ]


def _parse_batch_response(content: str) -> dict[int, float]:
    """Parse LLM JSON → {candidate_idx: score}. Raises on schema violation.

    Args:
        content: Raw JSON string from LLM response.

    Returns:
        Mapping from candidate index to score.

    Raises:
        ValidationError: If the JSON does not conform to L3BatchResult schema.
    """
    result = L3BatchResult.model_validate_json(content)
    return {item.candidate_idx: item.score for item in result.scores}


def _merge_scores(
    c2: list[dict[str, Any]],
    llm_scores: dict[int, float],
    theta_3: float,
) -> list[dict[str, Any]]:
    """Attach S3 scores to C2 entries. Missing idx → excluded. Filter by theta_3.

    Args:
        c2: Layer 2 candidates (1-indexed by position).
        llm_scores: {1-based candidate_idx: score} from LLM.
        theta_3: S₃ threshold; candidates below this are excluded.

    Returns:
        Filtered list with s3 score attached to each surviving entry.
    """
    c3 = []
    for i, cand in enumerate(c2, start=1):
        s3 = llm_scores.get(i, 0.0)
        if s3 > theta_3:
            c3.append({**cand, "s3": s3})
    return c3


async def batch_verify(
    *,
    c2: list[dict[str, Any]],
    query_name: str,
    query_cols: list[dict[str, Any]],
    task_type: Literal["JOIN", "UNION"],
    theta_3: float,
    batch_size: int = _BATCH_SIZE,
) -> list[dict[str, Any]]:
    """Run LLM batch verification on C₂, return C₃ with S₃ scores.

    Args:
        c2: Layer 2 candidates, each with {table_id, table_name, columns, s1, s2}.
        query_name: Query table name for prompt.
        query_cols: Query columns list [{name, dtype}].
        task_type: JOIN or UNION — determines prompt framing.
        theta_3: S₃ threshold.
        batch_size: Max candidates per LLM call (≤ 10).

    Returns:
        C₃ list with {table_id, s1, s2, s3} for items where S₃ > θ₃.
    """
    if not c2:
        return []

    # Split into batches
    batches = [c2[i:i + batch_size] for i in range(0, len(c2), batch_size)]
    offsets = list(range(0, len(c2), batch_size))

    async def _call_one(batch: list[dict[str, Any]], offset: int) -> dict[int, float]:
        messages = _build_batch_prompt(query_name, query_cols, batch, task_type, offset)
        try:
            resp = chat(
                messages,
                response_format=json_schema_format(L3BatchResult),
                temperature=0.0,
                enable_thinking=False,
            )
            content = resp.choices[0].message.content or "{}"
            return _parse_batch_response(content)
        except Exception as e:
            log.warning("retrieval.l3.batch_error", error=str(e), offset=offset)
            return {}

    # Parallel LLM calls
    results: list[dict[int, float]] = await asyncio.gather(
        *[_call_one(batch, off) for batch, off in zip(batches, offsets)]
    )

    # Merge all batch scores (re-index globally)
    global_scores: dict[int, float] = {}
    for batch_scores, offset in zip(results, offsets):
        for local_idx, score in batch_scores.items():
            global_idx = offset + local_idx
            global_scores[global_idx] = score

    c3 = _merge_scores(c2, global_scores, theta_3)
    log.info("retrieval.l3", c2_size=len(c2), c3_size=len(c3), theta_3=theta_3)
    return c3
