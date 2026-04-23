"""Module-level Qdrant singleton for use in LangGraph nodes."""

from __future__ import annotations

from adacascade.indexing.qdrant_client import AdacQdrantClient

_qdrant: AdacQdrantClient | None = None


def init_qdrant_registry(client: AdacQdrantClient) -> None:
    """Register the already-constructed Qdrant client as the module singleton.

    Call once at FastAPI startup after building the :class:`AdacQdrantClient`.

    Args:
        client: The initialized :class:`AdacQdrantClient` instance.
    """
    global _qdrant
    _qdrant = client


def get_qdrant() -> AdacQdrantClient:
    """Return the module-level Qdrant client.

    Returns:
        The singleton :class:`AdacQdrantClient`.

    Raises:
        RuntimeError: If :func:`init_qdrant_registry` has not been called yet.
    """
    if _qdrant is None:
        raise RuntimeError("Qdrant not initialized — call init_qdrant_registry() first")
    return _qdrant
