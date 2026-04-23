"""MatcherAgent — adaptive schema matching (Algorithm Spec §4).

M1: stub returning empty mappings. Full implementation in M2.
"""

from __future__ import annotations

import structlog

from adacascade.state import IntegrationState

log = structlog.get_logger(__name__)


async def run(state: IntegrationState) -> IntegrationState:
    """LangGraph node: Matcher stub for M1."""
    log.info("matcher.stub", task_id=state.get("task_id"))
    return {
        **state,
        "similarity_matrix_path": None,
        "final_mappings": [],
    }
