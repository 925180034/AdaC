#!/usr/bin/env python3
"""Initialize Qdrant collections and payload indexes."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from adacascade.config import settings


def main() -> None:
    """Create tbl_embeddings and col_embeddings collections with payload indexes."""
    client = QdrantClient(url=settings.QDRANT_URL)

    collections = {
        settings.QDRANT_COLLECTION_TABLES: [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("table_id", PayloadSchemaType.KEYWORD),
            ("status", PayloadSchemaType.KEYWORD),
        ],
        settings.QDRANT_COLLECTION_COLUMNS: [
            ("tenant_id", PayloadSchemaType.KEYWORD),
            ("table_id", PayloadSchemaType.KEYWORD),
            ("column_id", PayloadSchemaType.KEYWORD),
            ("status", PayloadSchemaType.KEYWORD),
            ("col_type", PayloadSchemaType.KEYWORD),
        ],
    }

    for name, indexes in collections.items():
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            print(f"[init_qdrant] Created collection: {name}")
        else:
            print(f"[init_qdrant] Collection already exists: {name}")

        for field, schema in indexes:
            client.create_payload_index(name, field, schema)
            print(f"[init_qdrant]   Index: {name}.{field}")

    print("[init_qdrant] Done.")


if __name__ == "__main__":
    main()
