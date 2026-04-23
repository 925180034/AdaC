"""RetrievalAgent — TLCF three-layer cascaded filtering (Algorithm Spec §3).

M1: stub returning empty results. Full implementation in M2.
"""

from __future__ import annotations

import structlog

from adacascade.state import IntegrationState

log = structlog.get_logger(__name__)


async def run(state: IntegrationState) -> IntegrationState:
    """LangGraph node: TLCF stub for M1."""
    log.info("retrieval.stub", task_id=state.get("task_id"))
    return {
        **state,
        "c1_meta": [],
        "c2_vec": [],
        "c3_llm": [],
        "ranking": [],
        "degraded": False,
    }
