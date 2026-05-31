"""Module-level DB session singleton for use in LangGraph nodes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_SessionFactory: sessionmaker[Session] | None = None


def _configure_sqlite_pragmas(engine: Engine, database_url: str) -> None:
    """Configure SQLite for deployment write contention tolerance."""
    if not database_url.startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def _copy_table_registry_without_legacy_unique_constraint(
    connection: Connection,
) -> None:
    """Rebuild legacy SQLite table_registry without tenant-wide content uniqueness."""
    connection.execute(
        text("ALTER TABLE table_registry RENAME TO table_registry_legacy")
    )
    connection.execute(
        text(
            """
            CREATE TABLE table_registry (
                table_id VARCHAR NOT NULL,
                tenant_id VARCHAR NOT NULL,
                dataset_id VARCHAR,
                source_system VARCHAR NOT NULL,
                source_uri VARCHAR NOT NULL,
                table_name VARCHAR NOT NULL,
                row_count INTEGER,
                col_count INTEGER,
                schema_hash VARCHAR,
                content_hash VARCHAR,
                uploaded_by VARCHAR,
                uploaded_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                status VARCHAR NOT NULL,
                PRIMARY KEY (table_id),
                CONSTRAINT ck_tr_status CHECK (status IN ('PENDING','INGESTED','PROFILING','READY','FAILED','ARCHIVED','REJECTED')),
                FOREIGN KEY(dataset_id) REFERENCES dataset_registry (dataset_id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO table_registry (
                table_id, tenant_id, dataset_id, source_system, source_uri, table_name,
                row_count, col_count, schema_hash, content_hash, uploaded_by,
                uploaded_at, updated_at, status
            )
            SELECT
                table_id, tenant_id, dataset_id, source_system, source_uri, table_name,
                row_count, col_count, schema_hash, content_hash, uploaded_by,
                uploaded_at, updated_at, status
            FROM table_registry_legacy
            """
        )
    )
    connection.execute(text("DROP TABLE table_registry_legacy"))


def _ensure_sqlite_schema_compatibility(engine: Engine) -> None:
    """Add nullable columns needed by newer models to existing SQLite DBs."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "table_registry" not in inspector.get_table_names():
        return

    table_columns = {
        column["name"] for column in inspector.get_columns("table_registry")
    }
    with engine.begin() as connection:
        if "dataset_id" not in table_columns:
            connection.execute(
                text("ALTER TABLE table_registry ADD COLUMN dataset_id VARCHAR")
            )
            inspector = inspect(engine)
        sqlite_indexes = connection.execute(
            text("PRAGMA index_list('table_registry')")
        ).fetchall()
        indexed_columns = [
            [
                column[2]
                for column in connection.execute(
                    text(f"PRAGMA index_info('{index[1]}')")
                ).fetchall()
            ]
            for index in sqlite_indexes
        ]
        has_legacy_unique_constraint = ["tenant_id", "content_hash"] in indexed_columns
        if has_legacy_unique_constraint:
            _copy_table_registry_without_legacy_unique_constraint(connection)
            inspector = inspect(engine)
        existing_indexes = {
            index[1]
            for index in connection.execute(
                text("PRAGMA index_list('table_registry')")
            ).fetchall()
        }
        if "ix_tr_tenant_status" not in existing_indexes:
            connection.execute(
                text(
                    "CREATE INDEX ix_tr_tenant_status ON table_registry (tenant_id, status)"
                )
            )
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
    _configure_sqlite_pragmas(engine, database_url)
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
