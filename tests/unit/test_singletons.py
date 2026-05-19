"""Tests for module-level DB and Qdrant singletons."""

from __future__ import annotations

import sqlite3

import pytest


def test_get_session_raises_before_init() -> None:
    """get_session() must raise RuntimeError when _SessionFactory is None."""
    import adacascade.db.session as mod

    mod._SessionFactory = None
    with pytest.raises(RuntimeError, match="DB not initialized"):
        with mod.get_session():
            pass


def test_get_qdrant_raises_before_init() -> None:
    """get_qdrant() must raise RuntimeError when _qdrant is None."""
    import adacascade.indexing.registry as mod

    mod._qdrant = None
    with pytest.raises(RuntimeError, match="Qdrant not initialized"):
        mod.get_qdrant()


def test_get_session_happy_path() -> None:
    """get_session() yields a working session after init_db()."""
    import adacascade.db.session as mod

    mod.init_db("sqlite:///:memory:")
    with mod.get_session() as db:
        assert db is not None


def test_init_db_removes_legacy_tenant_content_unique_constraint(tmp_path) -> None:
    """Dataset uploads may reuse table content across different Datasets."""
    import adacascade.db.session as mod

    db_path = tmp_path / "metadata.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE table_registry (
            table_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
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
            UNIQUE (tenant_id, content_hash)
        )
        """
    )
    connection.commit()
    connection.close()

    mod.init_db(f"sqlite:///{db_path}")

    connection = sqlite3.connect(db_path)
    try:
        indexes = connection.execute("PRAGMA index_list('table_registry')").fetchall()
        indexed_columns = [
            [column[2] for column in connection.execute(f"PRAGMA index_info('{index[1]}')").fetchall()]
            for index in indexes
        ]
    finally:
        connection.close()
    assert ["tenant_id", "content_hash"] not in indexed_columns
    assert ["tenant_id", "dataset_id", "content_hash"] in indexed_columns
