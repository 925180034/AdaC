"""Module-level DB session singleton for use in LangGraph nodes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_SessionFactory: sessionmaker[Session] | None = None


def _ensure_sqlite_schema_compatibility(engine: Engine) -> None:
    """Add nullable columns needed by newer models to existing SQLite DBs."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "table_registry" not in inspector.get_table_names():
        return

    table_columns = {column["name"] for column in inspector.get_columns("table_registry")}
    with engine.begin() as connection:
        if "dataset_id" not in table_columns:
            connection.execute(text("ALTER TABLE table_registry ADD COLUMN dataset_id VARCHAR"))
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("table_registry")
        }
        if "ix_tr_dataset_content" not in existing_indexes:
            connection.execute(
                text(
                    "CREATE INDEX ix_tr_dataset_content "
                    "ON table_registry (tenant_id, dataset_id, content_hash)"
                )
            )


def init_db(database_url: str) -> None:
    """Initialize the DB engine and create all tables.

    Call once at FastAPI startup. Subsequent calls overwrite the factory.

    Args:
        database_url: SQLAlchemy database URL (e.g. ``sqlite:///./data/meta.db``).
    """
    global _SessionFactory
    from adacascade.db.models import Base

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    _ensure_sqlite_schema_compatibility(engine)
    _SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a DB session; commit on success, rollback on exception.

    Yields:
        A SQLAlchemy :class:`Session` bound to the module-level engine.

    Raises:
        RuntimeError: If :func:`init_db` has not been called yet.
    """
    if _SessionFactory is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    db: Session = _SessionFactory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
