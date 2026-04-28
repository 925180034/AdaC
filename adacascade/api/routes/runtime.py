"""Runtime configuration API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adacascade import llm_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"])


class LlmRuntimeUpdate(BaseModel):
    backend: Literal["local", "api"]


@router.get("/llm")
async def get_llm_runtime() -> llm_runtime.RuntimeInfo:
    """Return safe LLM runtime metadata."""
    return llm_runtime.get_runtime_info()


@router.put("/llm")
async def update_llm_runtime(payload: LlmRuntimeUpdate) -> llm_runtime.RuntimeInfo:
    """Switch the process-local LLM runtime backend."""
    try:
        return llm_runtime.set_active_backend(payload.backend)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
