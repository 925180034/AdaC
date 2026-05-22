from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adacascade.db.models import Base, ColumnMetadata, TableRegistry


def _table(
    table_id: str,
    *,
    tenant_id: str = "benchmark",
    source_system: str = "test",
    table_name: str | None = None,
    status: str = "INGESTED",
) -> TableRegistry:
    now = datetime.now(timezone.utc)
    return TableRegistry(
        table_id=table_id,
        tenant_id=tenant_id,
        source_system=source_system,
        source_uri=f"/tmp/{table_id}.parquet",
        table_name=table_name or table_id,
        row_count=1,
        col_count=1,
        uploaded_at=now,
        updated_at=now,
        status=status,
    )


def test_save_pkl_sanitizes_artifact_name(tmp_path: Path, monkeypatch) -> None:
    import adacascade.artifacts as artifacts

    monkeypatch.setattr(artifacts.settings, "ARTIFACTS_DIR", str(tmp_path))

    path = artifacts.save_pkl("table", "freq_table:0:line/ramp", {"x": 1})

    assert Path(path).parent == tmp_path / "table"
    assert Path(path).name == "freq_table_0_line_ramp.pkl"


def test_qdrant_table_points_use_valid_point_ids() -> None:
    from qdrant_client.models import PointStruct

    from adacascade.indexing.qdrant_client import _table_point_id

    raw_table_id = "mimic:ADMISSIONS"
    point_id = _table_point_id(raw_table_id)

    UUID(point_id)
    PointStruct(id=point_id, vector=[0.1, 0.2], payload={"table_id": raw_table_id})
    assert point_id == _table_point_id(raw_table_id)


def test_qdrant_column_points_use_valid_point_ids() -> None:
    from qdrant_client.models import PointStruct

    from adacascade.indexing.qdrant_client import _column_point_id

    raw_column_id = "02925079-4773-5656-9e47-de00eacdf489:0:R"
    point_id = _column_point_id(raw_column_id)

    UUID(point_id)
    PointStruct(id=point_id, vector=[0.1, 0.2], payload={"column_id": raw_column_id})
    assert point_id == _column_point_id(raw_column_id)


class RecordingQdrant:
    def __init__(self) -> None:
        self.tables: list[dict] = []
        self.columns: list[list[dict]] = []

    async def upsert_table(self, **kwargs) -> None:
        self.tables.append(kwargs)

    async def upsert_columns(self, *, points: list[dict]) -> None:
        self.columns.append(points)


def _session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_profile_ingested_processes_ingested_tables_for_tenant(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts import profile_ingested

    db = _session(tmp_path)
    db.add_all(
        [
            _table("benchmark-table", tenant_id="benchmark", table_name="benchmark"),
            _table("default-table", tenant_id="default", table_name="default"),
        ]
    )
    db.commit()
    processed: list[tuple[str, str]] = []

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):
        processed.append((table_id, tenant_id))
        db.query(TableRegistry).filter_by(table_id=table_id).update({"status": "READY"})
        db.commit()

    monkeypatch.setattr(profile_ingested, "run_profiling", fake_run_profiling)

    summary = profile_ingested.profile_ingested_tables(
        db,
        qdrant=RecordingQdrant(),
        tenant_id="benchmark",
    )

    statuses = {row.table_id: row.status for row in db.query(TableRegistry).all()}
    assert summary == {"processed": 1, "succeeded": 1, "failed": 0}
    assert processed == [("benchmark-table", "benchmark")]
    assert statuses == {"benchmark-table": "READY", "default-table": "INGESTED"}


def test_profile_ingested_refresh_ready_reprofiles_ready_tables(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts import profile_ingested

    db = _session(tmp_path)
    db.add(_table("ready-table", status="READY"))
    db.commit()
    processed: list[str] = []

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):
        processed.append(table_id)
        assert db.query(TableRegistry).filter_by(table_id=table_id).one().status == "INGESTED"
        db.query(TableRegistry).filter_by(table_id=table_id).update({"status": "READY"})
        db.commit()

    monkeypatch.setattr(profile_ingested, "run_profiling", fake_run_profiling)

    summary = profile_ingested.profile_ingested_tables(
        db,
        qdrant=RecordingQdrant(),
        tenant_id="benchmark",
        refresh_ready=True,
    )

    assert summary == {"processed": 1, "succeeded": 1, "failed": 0}
    assert processed == ["ready-table"]
    assert db.query(TableRegistry).filter_by(table_id="ready-table").one().status == "READY"



def test_profile_ingested_refresh_ready_skips_schema_only_tables(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts import profile_ingested

    db = _session(tmp_path)
    db.add(
        _table(
            "schema-table",
            status="READY",
            source_system="mimic_omop",
        )
    )
    db.query(TableRegistry).filter_by(table_id="schema-table").update(
        {"source_uri": str(tmp_path / "schema.json")}
    )
    db.commit()

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):
        raise AssertionError("schema-only tables should not be profiled as parquet")

    monkeypatch.setattr(profile_ingested, "run_profiling", fake_run_profiling)

    summary = profile_ingested.profile_ingested_tables(
        db,
        qdrant=RecordingQdrant(),
        tenant_id="benchmark",
        refresh_ready=True,
    )

    assert summary == {"processed": 0, "succeeded": 0, "failed": 0}
    assert db.query(TableRegistry).filter_by(table_id="schema-table").one().status == "READY"



def test_profile_ingested_retry_failed_resets_failed_parquet_tables(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts import profile_ingested

    db = _session(tmp_path)
    db.add(_table("failed-table", status="FAILED"))
    db.add(_table("failed-schema-table", status="FAILED", source_system="mimic_omop"))
    db.query(TableRegistry).filter_by(table_id="failed-schema-table").update(
        {"source_uri": str(tmp_path / "schema.json")}
    )
    db.commit()
    processed: list[str] = []

    async def fake_run_profiling(*, table_id, db, qdrant, tenant_id):
        processed.append(table_id)
        assert (
            db.query(TableRegistry).filter_by(table_id=table_id).one().status
            == "INGESTED"
        )
        db.query(TableRegistry).filter_by(table_id=table_id).update({"status": "READY"})
        db.commit()

    monkeypatch.setattr(profile_ingested, "run_profiling", fake_run_profiling)

    summary = profile_ingested.profile_ingested_tables(
        db,
        qdrant=RecordingQdrant(),
        tenant_id="benchmark",
        retry_failed=True,
    )

    assert summary == {"processed": 1, "succeeded": 1, "failed": 0}
    assert processed == ["failed-table"]
    assert (
        db.query(TableRegistry).filter_by(table_id="failed-table").one().status
        == "READY"
    )
    assert (
        db.query(TableRegistry).filter_by(table_id="failed-schema-table").one().status
        == "FAILED"
    )


def test_ingest_schema_only_tables_create_ready_profiles_without_stats(
    tmp_path: Path,
) -> None:
    from adacascade.agents.profiling import load_table_profile
    from scripts.schema_only_ingest import ingest_schema_only_tables

    schema_path = tmp_path / "mimic_schema.json"
    schema_path.write_text(
        json.dumps(
            [
                {
                    "table_name": "ADMISSIONS",
                    "table_desc": "Hospital admissions.",
                    "columns": [
                        {
                            "ordinal": 0,
                            "name": "SUBJECT_ID",
                            "type": "integer",
                            "description": "Patient identifier.",
                        },
                        {
                            "ordinal": 1,
                            "name": "ADMITTIME",
                            "type": "timestamp",
                            "description": "Admission time.",
                        },
                    ],
                }
            ]
        )
    )
    db = _session(tmp_path)

    summary = ingest_schema_only_tables(
        db,
        schema_path,
        tenant_id="benchmark",
        source_system="mimic_omop",
        table_prefix="mimic",
    )

    table = db.query(TableRegistry).one()
    columns = db.query(ColumnMetadata).order_by(ColumnMetadata.ordinal).all()
    assert summary == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "table_ids": ["mimic:ADMISSIONS"],
    }
    assert table.table_id == "mimic:ADMISSIONS"
    assert table.tenant_id == "benchmark"
    assert table.source_system == "mimic_omop"
    assert table.source_uri == str(schema_path)
    assert table.status == "READY"
    assert table.row_count == 0
    assert table.col_count == 2
    assert [column.col_name for column in columns] == ["SUBJECT_ID", "ADMITTIME"]
    assert columns[0].col_description == "Patient identifier."
    profile = load_table_profile("mimic:ADMISSIONS", db)
    assert columns[0].null_ratio is None
    assert columns[0].distinct_ratio is None
    assert columns[0].stat_summary is None
    assert profile["text_blob"] == (
        "admissions subject_id patient identifier. admittime admission time."
    )
    assert profile["columns"][0]["numeric_stats"] is None
    assert profile["columns"][0]["categorical_stats"] is None
    assert profile["columns"][0]["sample_values"] == []


def test_index_schema_only_tables_upserts_embeddings(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts.schema_only_ingest import (
        index_schema_only_tables,
        ingest_schema_only_tables,
    )

    class FakeModel:
        def encode(self, texts, *, batch_size, normalize_embeddings):
            assert normalize_embeddings is True
            return [[float(index), 0.0] for index, _ in enumerate(texts, start=1)]

    monkeypatch.setattr("adacascade.agents.profiling._sbert", FakeModel())
    schema_path = tmp_path / "mimic_schema.json"
    schema_path.write_text(
        json.dumps(
            [
                {
                    "table_name": "ADMISSIONS",
                    "columns": [
                        {
                            "ordinal": 0,
                            "name": "SUBJECT_ID",
                            "type": "integer",
                            "description": "Patient identifier.",
                        }
                    ],
                }
            ]
        )
    )
    db = _session(tmp_path)
    qdrant = RecordingQdrant()
    ingest_schema_only_tables(
        db,
        schema_path,
        tenant_id="benchmark",
        source_system="mimic_omop",
        table_prefix="mimic",
    )

    summary = index_schema_only_tables(
        db,
        qdrant=qdrant,
        tenant_id="benchmark",
        source_system="mimic_omop",
    )

    columns = db.query(ColumnMetadata).all()
    assert summary == {"indexed": 1}
    assert qdrant.tables[0]["table_id"] == "mimic:ADMISSIONS"
    assert qdrant.tables[0]["tenant_id"] == "benchmark"
    assert qdrant.tables[0]["extra_payload"]["source_system"] == "mimic_omop"
    assert qdrant.columns[0][0]["column_id"] == "mimic:ADMISSIONS:0:SUBJECT_ID"
    assert columns[0].qdrant_point_id == "mimic:ADMISSIONS:0:SUBJECT_ID"


def test_index_schema_only_tables_can_scope_to_table_ids(
    monkeypatch, tmp_path: Path
) -> None:
    from scripts.schema_only_ingest import (
        index_schema_only_tables,
        ingest_schema_only_tables,
    )

    class FakeModel:
        def encode(self, texts, *, batch_size, normalize_embeddings):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("adacascade.agents.profiling._sbert", FakeModel())
    first_schema = tmp_path / "first_schema.json"
    second_schema = tmp_path / "second_schema.json"
    first_schema.write_text(
        json.dumps(
            [{"table_name": "ADMISSIONS", "columns": [{"ordinal": 0, "name": "ID"}]}]
        )
    )
    second_schema.write_text(
        json.dumps(
            [{"table_name": "PATIENTS", "columns": [{"ordinal": 0, "name": "ID"}]}]
        )
    )
    db = _session(tmp_path)
    qdrant = RecordingQdrant()
    ingest_schema_only_tables(
        db,
        first_schema,
        tenant_id="benchmark",
        source_system="mimic_omop",
        table_prefix="mimic",
    )
    ingest_schema_only_tables(
        db,
        second_schema,
        tenant_id="benchmark",
        source_system="mimic_omop",
        table_prefix="mimic",
    )

    summary = index_schema_only_tables(
        db,
        qdrant=qdrant,
        tenant_id="benchmark",
        source_system="mimic_omop",
        table_ids=["mimic:ADMISSIONS"],
    )

    assert summary == {"indexed": 1}
    assert [table["table_id"] for table in qdrant.tables] == ["mimic:ADMISSIONS"]


def test_retrieval_l1_can_load_corpus_scoped_tfidf(tmp_path: Path) -> None:
    from scripts.rebuild_tfidf import rebuild_tfidf
    from adacascade.agents.retrieval import layer1

    db = _session(tmp_path)
    db.add_all(
        [
            _table(
                "join-table",
                source_system="retrieval|join",
                table_name="join musicians",
                status="READY",
            ),
            _table(
                "union-table",
                source_system="retrieval|union",
                table_name="union albums",
                status="READY",
            ),
        ]
    )
    db.add_all(
        [
            ColumnMetadata(
                column_id="join-table:0:id",
                table_id="join-table",
                ordinal=0,
                col_name="join_only",
                col_type="str",
            ),
            ColumnMetadata(
                column_id="union-table:0:id",
                table_id="union-table",
                ordinal=0,
                col_name="union_only",
                col_type="str",
            ),
        ]
    )
    db.commit()
    rebuild_tfidf(
        db,
        tenant_id="benchmark",
        corpus="join",
        artifacts_dir=tmp_path / "artifacts",
    )

    vectorizer = layer1.load_tfidf(
        tenant_id="benchmark",
        corpus="join",
        artifacts_dir=tmp_path / "artifacts",
    )

    assert "join_only" in vectorizer.vocabulary_
    assert "union_only" not in vectorizer.vocabulary_


def test_rebuild_tfidf_writes_corpus_scoped_artifact(tmp_path: Path) -> None:
    from scripts.rebuild_tfidf import rebuild_tfidf

    db = _session(tmp_path)
    db.add_all(
        [
            _table(
                "join-table",
                source_system="retrieval|join",
                table_name="join musicians",
                status="READY",
            ),
            _table(
                "union-table",
                source_system="retrieval|union",
                table_name="union albums",
                status="READY",
            ),
        ]
    )
    db.add_all(
        [
            ColumnMetadata(
                column_id="join-table:0:id",
                table_id="join-table",
                ordinal=0,
                col_name="join_only",
                col_type="str",
            ),
            ColumnMetadata(
                column_id="union-table:0:id",
                table_id="union-table",
                ordinal=0,
                col_name="union_only",
                col_type="str",
            ),
        ]
    )
    db.commit()

    result = rebuild_tfidf(
        db,
        tenant_id="benchmark",
        corpus="join",
        artifacts_dir=tmp_path / "artifacts",
    )

    assert result["tables"] == 1
    assert result["path"] == str(tmp_path / "artifacts" / "tfidf_benchmark_join.pkl")
    assert "join_only" in result["vocabulary"]
    assert "union_only" not in result["vocabulary"]
