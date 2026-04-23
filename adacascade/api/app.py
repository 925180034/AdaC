"""FastAPI application with lifespan — Qdrant + LangGraph + reconciliation.

See System Design §4.3 for the full lifespan design.
IMPORTANT: Must run with --workers 1 (see CLAUDE.md §3).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from qdrant_client import AsyncQdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.api.routes import tables
from adacascade.config import settings
from adacascade.db.models import Base, TableRegistry
from adacascade.graph.build import build_graph
from adacascade.indexing.qdrant_client import AdacQdrantClient
from adacascade.ingest.reconcile import reconcile_orphan_ingests

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan: initialize all shared resources."""
    # ── 1. SQLite engine + sessionmaker ──────────────────────────────────────
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)  # idempotent
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    app.state.db_session_factory = SessionFactory

    # ── 2. Qdrant client ──────────────────────────────────────────────────────
    raw_qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)
    app.state.qdrant = AdacQdrantClient(raw_qdrant)

    # ── 3. LangGraph checkpoint + compiled graph ──────────────────────────────
    async with AsyncSqliteSaver.from_conn_string(settings.CKPT_PATH) as ckpt:
        app.state.graph = build_graph().compile(checkpointer=ckpt)
        log.info("app.startup", qdrant_url=settings.QDRANT_URL)

        # ── 4. Reconcile orphan INGESTED tasks ─────────────────────────────────
        db = SessionFactory()
        try:
            async def _enqueue(table_id: str) -> None:
                from adacascade.agents.profiling import run_profiling
                # Tenant will be read from DB inside run_profiling
                tr = db.query(TableRegistry).filter_by(table_id=table_id).first()
                tenant_id = tr.tenant_id if tr else settings.DEFAULT_TENANT_ID
                await run_profiling(
                    table_id=table_id,
                    db=db,
                    qdrant=app.state.qdrant,
                    tenant_id=tenant_id,
                )

            requeued = await reconcile_orphan_ingests(db, _enqueue)
            log.info("app.reconcile", requeued=requeued)
        finally:
            db.close()

        yield

    # ── Cleanup ───────────────────────────────────────────────────────────────
    await raw_qdrant.close()
    log.info("app.shutdown")


app = FastAPI(
    title="AdaCascade",
    description="Adaptive cascaded filtering for data lake table discovery and schema matching.",
    version="2.2.0",
    lifespan=lifespan,
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(tables.router)


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
