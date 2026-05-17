#!/usr/bin/env python3
"""Upload the generated smart agriculture demo lake into an AdaCascade Dataset."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin

import requests

DEFAULT_ROOT = Path("demo_data/agri_lake")
DEFAULT_API_BASE_URL = "http://localhost:6008"
DEFAULT_TOKEN = "dev-local-token"
DEFAULT_TENANT = "default"


@dataclass
class UploadRequest:
    url: str
    headers: dict[str, str]
    data: dict[str, str]
    files: list[tuple[str, tuple[str, BinaryIO, str]]]


def _csv_paths(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*/*.csv") if path.is_file())


def build_upload_request(
    *,
    root: Path,
    api_base_url: str,
    tenant_id: str,
    dataset_id: str,
    uploaded_by: str | None = None,
    token: str = DEFAULT_TOKEN,
    table_name_prefix: str | None = None,
) -> UploadRequest:
    csv_paths = _csv_paths(root)
    if not csv_paths:
        raise ValueError(f"No CSV files found under {root}")

    data: dict[str, str] = {}
    if uploaded_by:
        data["uploaded_by"] = uploaded_by
    if table_name_prefix:
        data["table_name_prefix"] = table_name_prefix

    files = [
        ("files", (csv_path.name, csv_path.open("rb"), "text/csv"))
        for csv_path in csv_paths
    ]
    return UploadRequest(
        url=urljoin(api_base_url.rstrip("/") + "/", f"datasets/{dataset_id}/tables"),
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": tenant_id},
        data=data,
        files=files,
    )


def _close_files(files: list[tuple[str, tuple[str, BinaryIO, str]]]) -> None:
    for _, (_, handle, _) in files:
        handle.close()


def upload_agri_demo(
    *,
    root: Path,
    api_base_url: str,
    tenant_id: str,
    dataset_id: str,
    uploaded_by: str | None,
    token: str,
    table_name_prefix: str | None,
) -> dict[str, int]:
    request = build_upload_request(
        root=root,
        api_base_url=api_base_url,
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        uploaded_by=uploaded_by,
        token=token,
        table_name_prefix=table_name_prefix,
    )
    try:
        response = requests.post(
            request.url,
            headers=request.headers,
            data=request.data,
            files=request.files,
            timeout=300,
        )
    finally:
        _close_files(request.files)

    if response.status_code >= 400:
        raise RuntimeError(f"Upload failed with {response.status_code}: {response.text}")

    payload = response.json()
    for item in payload.get("accepted", []):
        print(f"created {item.get('table_name')} {item.get('table_id')}")
    for item in payload.get("rejected", []):
        print(f"rejected {item.get('source')}: {item.get('reason')}")
    for item in payload.get("skipped", []):
        print(f"skipped {item.get('source')}: {item.get('reason')}")

    summary = {
        "created": len(payload.get("accepted", [])),
        "rejected": len(payload.get("rejected", [])),
        "skipped": len(payload.get("skipped", [])),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--uploaded-by", default="agri-demo-generator")
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--table-name-prefix")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    upload_agri_demo(
        root=args.root,
        api_base_url=args.api_base_url,
        tenant_id=args.tenant_id,
        dataset_id=args.dataset_id,
        uploaded_by=args.uploaded_by,
        token=args.token,
        table_name_prefix=args.table_name_prefix,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
