"""Module-level DB session singleton for use in LangGraph nodes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_SessionFactory: sessionmaker[Session] | None = None


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
