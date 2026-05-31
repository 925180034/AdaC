"""Regression tests for legacy POST /tables upload behavior."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.api.routes import tables
from adacascade.db.models import Base, TableRegistry


@pytest.fixture()
def db() -> Session:
    """Return an isolated in-memory database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


class _FakeQdrant:
    pass


class _FakeRequest:
    def __init__(self) -> None:
        self.state = SimpleNamespace(tenant_id="tenant-a")
        self.app = SimpleNamespace(state=SimpleNamespace(qdrant=_FakeQdrant()))


def _upload_file(payload: bytes) -> UploadFile:
    return UploadFile(filename="people.csv", file=io.BytesIO(payload))


@pytest.mark.anyio
async def test_upload_table_commits_before_scheduling_profiling(
    db: Session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profiling background sessions must be able to read the uploaded row."""
    monkeypatch.setattr(tables.settings, "DATA_DIR", str(tmp_path))
    scheduled: list[Any] = []

    class CapturingBackgroundTasks(BackgroundTasks):
        def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None:
            scheduled.append((func, args, kwargs))

    response = await tables.upload_table(
        request=_FakeRequest(),  # type: ignore[arg-type]
        background_tasks=CapturingBackgroundTasks(),
        file=_upload_file(b"id,name\n1,Ada\n"),
        table_name="people",
        source_system="upload",
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by="tester",
        col_descriptions=None,
        db=db,
    )

    assert response["status"] == "INGESTED"
    assert scheduled
    assert db.in_transaction() is False


@pytest.mark.anyio
async def test_upload_table_persists_dataset_id(
    db: Session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy upload endpoint should associate uploaded tables with Dataset."""
    monkeypatch.setattr(tables.settings, "DATA_DIR", str(tmp_path))

    response = await tables.upload_table(
        request=_FakeRequest(),  # type: ignore[arg-type]
        background_tasks=BackgroundTasks(),
        file=_upload_file(b"id,name\n1,Ada\n"),
        table_name="people",
        source_system="upload",
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by="tester",
        col_descriptions=None,
        db=db,
    )

    table = db.query(TableRegistry).filter_by(table_id=response["table_id"]).one()
    assert table.dataset_id == "dataset-a"
