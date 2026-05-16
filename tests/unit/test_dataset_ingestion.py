from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adacascade.db.models import Base, TableRegistry
from adacascade.ingest.pipeline import ingest_table, ingest_upload_bundle


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def csv_bytes(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


def parquet_bytes(frame: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()
    frame.to_parquet(output, index=False)
    output.seek(0)
    return output


def xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output


def zip_bytes(entries: dict[str, bytes]) -> io.BytesIO:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    output.seek(0)
    return output


def accepted_ids(summary: dict[str, Any]) -> list[str]:
    return [str(item["table_id"]) for item in summary["accepted"]]


def test_ingest_table_records_dataset_id_and_scopes_duplicate_content(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.ingest.pipeline.settings.DATA_DIR", str(tmp_path))

    first_id, first_status = ingest_table(
        file=csv_bytes("id,name\n1,Ada\n"),
        filename="people.csv",
        table_name="people",
        source_system="upload",
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by="tester",
        col_descriptions=None,
        db=db,
    )
    second_id, second_status = ingest_table(
        file=csv_bytes("id,name\n1,Ada\n"),
        filename="people.csv",
        table_name="people copy",
        source_system="upload",
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by="tester",
        col_descriptions=None,
        db=db,
    )
    third_id, third_status = ingest_table(
        file=csv_bytes("id,name\n1,Ada\n"),
        filename="people.csv",
        table_name="people other dataset",
        source_system="upload",
        tenant_id="tenant-a",
        dataset_id="dataset-b",
        uploaded_by="tester",
        col_descriptions=None,
        db=db,
    )

    assert first_status == "INGESTED"
    assert second_status == "REJECTED"
    assert third_status == "INGESTED"
    assert second_id == first_id
    assert third_id != first_id
    assert db.query(TableRegistry).filter_by(table_id=first_id).one().dataset_id == "dataset-a"
    assert db.query(TableRegistry).filter_by(table_id=third_id).one().dataset_id == "dataset-b"


@pytest.mark.parametrize(
    ("csv_text", "message"),
    [
        ("id,name\n", "at least one data row"),
        (",name\n1,Ada\n", "blank column name"),
        ("id,id\n1,2\n", "duplicate column name"),
    ],
)
def test_ingest_table_rejects_invalid_schema(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, csv_text: str, message: str
) -> None:
    monkeypatch.setattr("adacascade.ingest.pipeline.settings.DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match=message):
        ingest_table(
            file=csv_bytes(csv_text),
            filename="bad.csv",
            table_name="bad",
            source_system="upload",
            tenant_id="tenant-a",
            dataset_id="dataset-a",
            uploaded_by=None,
            col_descriptions=None,
            db=db,
        )


def test_ingest_upload_bundle_expands_excel_sheets(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.ingest.pipeline.settings.DATA_DIR", str(tmp_path))
    workbook = xlsx_bytes(
        {
            "People": pd.DataFrame({"id": [1], "name": ["Ada"]}),
            "Cities": pd.DataFrame({"city": ["London"]}),
        }
    )

    summary = ingest_upload_bundle(
        files=[("demo.xlsx", workbook.getvalue())],
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by="tester",
        table_name_prefix=None,
        db=db,
    )

    assert summary["dataset_id"] == "dataset-a"
    assert {item["table_name"] for item in summary["accepted"]} == {"demo__People", "demo__Cities"}
    assert summary["rejected"] == []
    assert summary["skipped"] == []
    assert len(accepted_ids(summary)) == 2


def test_ingest_upload_bundle_expands_zip_and_reports_skips(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("adacascade.ingest.pipeline.settings.DATA_DIR", str(tmp_path))
    archive = zip_bytes(
        {
            "people.csv": b"id,name\n1,Ada\n",
            "one/places.csv": b"id,place\n1,London\n",
            "one/two/deep.csv": b"id\n1\n",
            "notes.txt": b"skip me",
            "__MACOSX/._people.csv": b"skip me",
            ".hidden.csv": b"id\n1\n",
        }
    )

    summary = ingest_upload_bundle(
        files=[("bundle.zip", archive.getvalue())],
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by=None,
        table_name_prefix="batch",
        db=db,
    )

    assert {item["table_name"] for item in summary["accepted"]} == {"batch_people", "batch_places"}
    assert summary["rejected"] == []
    skipped_sources = {item["source"] for item in summary["skipped"]}
    assert {"one/two/deep.csv", "notes.txt", "__MACOSX/._people.csv", ".hidden.csv"} <= skipped_sources


def test_ingest_upload_bundle_rejects_one_bad_file_without_failing_batch(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("adacascade.ingest.pipeline.settings.DATA_DIR", str(tmp_path))

    summary = ingest_upload_bundle(
        files=[
            ("good.csv", b"id,name\n1,Ada\n"),
            ("bad.csv", b"id,id\n1,2\n"),
        ],
        tenant_id="tenant-a",
        dataset_id="dataset-a",
        uploaded_by=None,
        table_name_prefix=None,
        db=db,
    )

    assert [item["table_name"] for item in summary["accepted"]] == ["good"]
    assert summary["rejected"] == [{"source": "bad.csv", "reason": "duplicate column name: id"}]
    assert summary["skipped"] == []
