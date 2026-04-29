"""Runtime configuration API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adacascade import llm_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"])


class LlmRuntimeInfo(BaseModel):
    backend: Literal["local", "api"]
    base_url: str
    model: str
    api_key_configured: bool


class LlmRuntimeUpdate(BaseModel):
    backend: Literal["local", "api"]


@router.get("/llm")
async def get_llm_runtime() -> LlmRuntimeInfo:
    """Return safe LLM runtime metadata."""
    return LlmRuntimeInfo.model_validate(llm_runtime.get_runtime_info())


@router.put("/llm")
async def update_llm_runtime(payload: LlmRuntimeUpdate) -> LlmRuntimeInfo:
    """Switch the process-local LLM runtime backend."""
    try:
        return LlmRuntimeInfo.model_validate(
            llm_runtime.set_active_backend(payload.backend)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
