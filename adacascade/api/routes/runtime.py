"""Runtime configuration API routes."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adacascade import llm_runtime, local_llm_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"])
_runtime_update_lock = asyncio.Lock()


class LlmRuntimeInfo(BaseModel):
    backend: Literal["local", "api"]
    base_url: str
    model: str
    api_key_configured: bool
    local_status: Literal["stopped", "starting", "ready", "stopping", "error"]
    local_ready: bool
    local_last_error: str | None


class LlmRuntimeUpdate(BaseModel):
    backend: Literal["local", "api"]


def _runtime_info() -> LlmRuntimeInfo:
    payload = {
        **llm_runtime.get_runtime_info(),
        **local_llm_runtime.get_manager().snapshot(),
    }
    return LlmRuntimeInfo.model_validate(payload)


@router.get("/llm")
async def get_llm_runtime() -> LlmRuntimeInfo:
    """Return safe LLM runtime metadata."""
    return _runtime_info()


@router.put("/llm")
async def update_llm_runtime(payload: LlmRuntimeUpdate) -> LlmRuntimeInfo:
    """Switch the process-local LLM runtime backend."""
    manager = local_llm_runtime.get_manager()
    async with _runtime_update_lock:
        try:
            if payload.backend == "local":
                await manager.ensure_ready()
                llm_runtime.set_active_backend("local")
                return _runtime_info()

            llm_runtime.set_active_backend("api")
            await manager.stop_managed()
            return _runtime_info()
        except local_llm_runtime.LocalRuntimeError as exc:
            llm_runtime.set_active_backend("api")
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
