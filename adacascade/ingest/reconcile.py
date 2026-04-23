"""Startup reconciliation — re-queue orphaned INGESTED/PROFILING tables.

Called during FastAPI lifespan to recover tasks lost when the process crashed
mid-Profiling. This is a lightweight alternative to Taskiq/Celery (see
system_design §3.4 and CLAUDE.md §4).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from adacascade.db.models import TableRegistry

log = structlog.get_logger(__name__)


async def reconcile_orphan_ingests(
    db: Session,
    enqueue: Callable[[str], Coroutine[Any, Any, None]],
) -> int:
    """Scan for orphaned records and re-submit them for Profiling.

    Args:
        db: SQLAlchemy session.
        enqueue: Async callable that accepts a table_id and schedules Profiling.

    Returns:
        Number of tables re-queued.
    """
    # Reset PROFILING → INGESTED (process crashed mid-flight)
    db.execute(
        update(TableRegistry)
        .where(TableRegistry.status == "PROFILING")
        .values(status="INGESTED")
    )
    db.commit()

    orphans = (
        db.query(TableRegistry.table_id)
        .filter(TableRegistry.status == "INGESTED")
        .all()
    )

    count = 0
    for (table_id,) in orphans:
        log.info("reconcile.requeue", table_id=table_id)
        await enqueue(table_id)
        count += 1

    if count:
        log.info("reconcile.done", requeued=count)
    return count
