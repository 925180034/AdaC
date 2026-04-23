"""Tests for module-level DB and Qdrant singletons."""

from __future__ import annotations

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
