"""Qdrant client wrapper — upsert, search, delete with payload filtering."""

from __future__ import annotations

from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from adacascade.config import settings


def _table_point_id(table_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"adacascade:table:{table_id}"))


def _column_point_id(column_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"adacascade:column:{column_id}"))


class AdacQdrantClient:
    """Thin wrapper around AsyncQdrantClient for AdaCascade's two collections."""

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._q = client
        self._tbl = settings.QDRANT_COLLECTION_TABLES
        self._col = settings.QDRANT_COLLECTION_COLUMNS

    # ── Table-level ───────────────────────────────────────────────────────────

    async def upsert_table(
        self,
        *,
        table_id: str,
        tenant_id: str,
        vector: list[float],
        status: str = "READY",
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a table-level embedding into tbl_embeddings."""
        payload: dict[str, Any] = {
            "table_id": table_id,
            "tenant_id": tenant_id,
            "status": status,
        }
        if extra_payload:
            payload.update(extra_payload)
        await self._q.upsert(
            collection_name=self._tbl,
            points=[PointStruct(id=_table_point_id(table_id), vector=vector, payload=payload)],
        )

    async def search_tables(
        self,
        *,
        vector: list[float],
        tenant_id: str,
        top_k: int,
        source_system: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search table-level embeddings filtered by tenant and READY status."""
        must = [
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(key="status", match=MatchValue(value="READY")),
        ]
        if source_system:
            must.append(
                FieldCondition(key="source_system", match=MatchValue(value=source_system))
            )
        result = await self._q.query_points(
            collection_name=self._tbl,
            query=vector,
            query_filter=Filter(must=cast(Any, must)),
            limit=top_k,
            with_payload=True,
        )
        return [
            {"table_id": (p.payload or {})["table_id"], "score": p.score}
            for p in result.points
            if p.payload
        ]

    # ── Column-level ──────────────────────────────────────────────────────────

    async def upsert_columns(
        self,
        *,
        points: list[dict[str, Any]],
        status: str = "READY",
    ) -> None:
        """Batch-upsert column-level embeddings into col_embeddings."""
        structs = [
            PointStruct(
                id=_column_point_id(str(p["column_id"])),
                vector=p["vector"],
                payload={
                    "column_id": p["column_id"],
                    "table_id": p["table_id"],
                    "tenant_id": p["tenant_id"],
                    "col_type": p.get("col_type", "str"),
                    "status": status,
                    "source_system": p.get("source_system"),
                },
            )
            for p in points
        ]
        await self._q.upsert(collection_name=self._col, points=structs)

    async def search_columns(
        self,
        *,
        vector: list[float],
        tenant_id: str,
        top_k: int,
        source_system: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search column-level embeddings filtered by tenant and READY status."""
        must = [
            FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
            FieldCondition(key="status", match=MatchValue(value="READY")),
        ]
        if source_system:
            must.append(
                FieldCondition(key="source_system", match=MatchValue(value=source_system))
            )
        result = await self._q.query_points(
            collection_name=self._col,
            query=vector,
            query_filter=Filter(must=cast(Any, must)),
            limit=top_k,
            with_payload=True,
        )
        return [
            {
                "column_id": (p.payload or {})["column_id"],
                "table_id": (p.payload or {})["table_id"],
                "score": p.score,
            }
            for p in result.points
            if p.payload
        ]

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_table(self, *, table_id: str) -> None:
        """Hard-delete all vectors associated with a table (both collections)."""
        filt = Filter(
            must=[FieldCondition(key="table_id", match=MatchValue(value=table_id))]
        )
        await self._q.delete(collection_name=self._tbl, points_selector=filt)
        await self._q.delete(collection_name=self._col, points_selector=filt)

    async def update_status(self, *, table_id: str, status: str) -> None:
        """Update the status payload field for all vectors of a table."""
        filt = Filter(
            must=[FieldCondition(key="table_id", match=MatchValue(value=table_id))]
        )
        for collection in (self._tbl, self._col):
            await self._q.set_payload(
                collection_name=collection,
                payload={"status": status},
                points=filt,
            )
