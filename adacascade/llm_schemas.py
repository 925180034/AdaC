"""Pydantic schemas for all LLM structured outputs.

All LLM calls MUST use response_format={"type": "json_schema", ...} with
these models. Never use {"type": "json_object"} — see CLAUDE.md §2.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlannerDecision(BaseModel):
    """Planner subtask decision — JOIN vs UNION."""

    subtask: Literal["JOIN", "UNION"]
    reason: str = Field(max_length=60)


class L3CandidateScore(BaseModel):
    """Retrieval L3 score for a single candidate table."""

    candidate_idx: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=60)


class L3BatchResult(BaseModel):
    """Retrieval L3 batch LLM response."""

    scores: list[L3CandidateScore]


class MatchResult(BaseModel):
    """Matcher decision for a single column pair."""

    reasoning: str = Field(max_length=300)
    score: float = Field(ge=0.0, le=1.0)
    is_equivalent: bool


def json_schema_format(model: type[BaseModel], name: str | None = None) -> dict:
    """Build the response_format dict for vLLM JSON Schema constrained decoding."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name or model.__name__,
            "schema": model.model_json_schema(),
            "strict": True,
        },
    }
