"""SQLite-backed Matcher verification cache helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from adacascade.agents.matcher.mixed import Scenario
from adacascade.db.models import MatcherVerificationCache
from adacascade.db.session import get_session
from adacascade.llm_runtime import LlmRequestConfig
from adacascade.llm_schemas import MatchResult

log = structlog.get_logger(__name__)


def get(cache_key: str) -> MatchResult | None:
    """Return a cached Matcher verification result from SQLite."""
    try:
        with get_session() as db:
            row = db.get(MatcherVerificationCache, cache_key)
            if row is None:
                return None
            row.last_hit_at = datetime.now(timezone.utc)
            row.hit_count += 1
            return MatchResult.model_validate_json(row.result)
    except Exception as exc:
        log.warning("matcher.cache.sqlite_get_failed", cache_key=cache_key, error=str(exc))
        return None


def put(
    cache_key: str,
    *,
    runtime_config: LlmRequestConfig,
    prompt_version: str,
    scenario: Scenario,
    src_col: dict[str, Any],
    tgt_col: dict[str, Any],
    src_payload: dict[str, Any],
    tgt_payload: dict[str, Any],
    component_scores: dict[str, float],
    result: MatchResult,
) -> None:
    """Store or refresh a Matcher verification result in SQLite."""
    now = datetime.now(timezone.utc)
    try:
        with get_session() as db:
            row = db.get(MatcherVerificationCache, cache_key)
            if row is None:
                row = MatcherVerificationCache(cache_key=cache_key, created_at=now)
                db.add(row)
            row.backend = runtime_config.backend
            row.base_url = runtime_config.base_url
            row.model = runtime_config.model
            row.prompt_version = prompt_version
            row.scenario = scenario
            row.src_column_id = str(src_col.get("col_id") or "") or None
            row.tgt_column_id = str(tgt_col.get("col_id") or "") or None
            row.src_payload = json.dumps(src_payload, sort_keys=True, default=str)
            row.tgt_payload = json.dumps(tgt_payload, sort_keys=True, default=str)
            row.component_scores = json.dumps(component_scores, sort_keys=True)
            row.result = result.model_dump_json()
    except Exception as exc:
        log.warning("matcher.cache.sqlite_put_failed", cache_key=cache_key, error=str(exc))
