#!/usr/bin/env python3
"""
scripts/prepare_fixtures.py

Converts raw benchmark datasets into the unified Parquet + JSON layout
used by AdaCascade tests. Does NOT require Qdrant / vLLM / SQLite.

Output layout
-------------
tests/fixtures/
├── toy_lake/                  # 10 curated tables for M1 skeleton tests
│   ├── tables/{table_id}/
│   │   ├── data.parquet
│   │   └── manifest.json
│   └── ground_truth.json
├── retrieval_bench/           # WebTable-Noise  (TLCF §3.7 regression)
│   ├── join/
│   │   ├── tables/{table_id}/
│   │   ├── queries.json
│   │   └── ground_truth.json
│   └── union/
│       └── (same structure, table-level only)
└── matcher_bench/             # Wikidata + MIMIC-OMOP  (Matcher §4.9)
    ├── wikidata/
    │   ├── {scenario}/        # joinable / semjoinable / unionable / viewunion
    │   │   ├── source/{table_id}/
    │   │   ├── target/{table_id}/
    │   │   └── ground_truth.json
    │   └── ...
    └── mimic_omop/            # SMD (schema-only, no Parquet)
        ├── mimic_schema.json
        ├── omop_schema.json
        └── ground_truth.json

Storage contract (系统设计 §3.2 / §6.1)
----------------------------------------
- 行数据   → data.parquet
- 表/列元数据 → manifest.json  (供 init_db 批量导入，字段对应 table_registry / column_metadata)
- 标注数据   → ground_truth.json  (评测专用，不进生产 DB)
- SMD 无实例数据 → *_schema.json  (虚表，Profiling 走 SMD 路径)

Run
---
    python scripts/prepare_fixtures.py               # all
    python scripts/prepare_fixtures.py --only toy
    python scripts/prepare_fixtures.py --only retrieval
    python scripts/prepare_fixtures.py --only matcher
    python scripts/prepare_fixtures.py --skip-existing  # 跳过已转换的表
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS  = REPO_ROOT / "datasets"
FIXTURES  = REPO_ROOT / "tests" / "fixtures"

# Deterministic UUID5 namespace (固定值，保证重复运行 table_id 不变)
_UUID_NS = uuid.UUID("adac0000-0000-0000-0000-000000000001")

# Pandas dtype → 系统统一类型字符串 (算法规格 §2.1)
_DTYPE_MAP: dict[str, str] = {
    "int8": "int", "int16": "int", "int32": "int", "int64": "int",
    "uint8": "int", "uint16": "int", "uint32": "int", "uint64": "int",
    "float16": "float", "float32": "float", "float64": "float",
    "bool": "bool",
    "object": "str", "string": "str",
    "datetime64[ns]": "date", "datetime64[us]": "date",
}

# Wikidata 场景：(目录后缀, task_type, scenario)
_WIKI_SCENARIOS: list[tuple[str, str, str]] = [
    ("joinable",    "JOIN",  "SLD"),
    ("semjoinable", "JOIN",  "SLD"),
    ("unionable",   "UNION", "SLD"),
    ("viewunion",   "UNION", "SLD"),
]

# toy_lake：每张 Wikidata 表采样行数
_TOY_SAMPLE_ROWS = 300


# ── Utilities ──────────────────────────────────────────────────────────────────

def _stable_id(seed: str) -> str:
    """UUID5 from seed string — deterministic across runs."""
    return str(uuid.uuid5(_UUID_NS, seed))


def _infer_col_type(series: pd.Series) -> str:
    """Map pandas dtype to AdaCascade unified type string."""
    return _DTYPE_MAP.get(str(series.dtype), "str")


def _schema_hash(df: pd.DataFrame) -> str:
    """SHA-256 of 'col:type|...' — matches table_registry.schema_hash convention."""
    sig = "|".join(f"{c}:{_infer_col_type(df[c])}" for c in df.columns)
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


def _file_hash(path: Path) -> str:
    """SHA-256 of file bytes (first 16 hex chars)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _read_csv(path: Path, **kwargs) -> Optional[pd.DataFrame]:
    """Read CSV with UTF-8 / UTF-8-BOM / Latin-1 fallback."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False, **kwargs)
        except Exception:
            continue
    return None


def _save_table(
    df: pd.DataFrame,
    out_dir: Path,
    table_id: str,
    table_name: str,
    tenant_id: str,
    source: str,
    col_descriptions: Optional[dict[str, str]] = None,
) -> dict:
    """Write data.parquet + manifest.json; return manifest dict.

    Args:
        df: Table data.
        out_dir: Directory for this table (will be created).
        table_id: Stable UUID for this table.
        table_name: Human-readable name.
        tenant_id: Tenant identifier (e.g. "benchmark").
        source: Dataset origin label (e.g. "webtable", "wikidata").
        col_descriptions: Optional {col_name: description} from metadata.

    Returns:
        Manifest dict matching table_registry + column_metadata schema.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "data.parquet"
    df.to_parquet(parquet_path, index=False, engine="pyarrow")

    manifest: dict = {
        "table_id":    table_id,
        "table_name":  table_name,
        "tenant_id":   tenant_id,
        "source":      source,
        "row_count":   len(df),
        "col_count":   len(df.columns),
        "schema_hash": _schema_hash(df),
        "content_hash": _file_hash(parquet_path),
        "columns": [
            {
                "ordinal":     i,
                "name":        col,
                "type":        _infer_col_type(df[col]),
                "description": (col_descriptions or {}).get(col),
            }
            for i, col in enumerate(df.columns)
        ],
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return manifest


# ── 1. Toy Lake ────────────────────────────────────────────────────────────────

def _pick_clean_webtable_pairs(n: int) -> list[tuple[str, str, str, str]]:
    """Find N WebTable JOIN pairs where both columns exist in their CSV files.

    Args:
        n: Number of pairs to return.

    Returns:
        List of (query_table, candidate_table, query_col, cand_col).
    """
    gt_file = DATASETS / "dl" / "join" / "webtable_join_ground_truth.csv"
    tbl_dir = DATASETS / "dl" / "join" / "tables"
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str, str, str]] = []

    with open(gt_file, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["query_table"], row["candidate_table"])
            if key in seen:
                continue
            df_q = _read_csv(tbl_dir / row["query_table"], nrows=0)
            df_c = _read_csv(tbl_dir / row["candidate_table"], nrows=0)
            if df_q is None or df_c is None:
                continue
            if (
                row["query_column"] in df_q.columns
                and row["candidate_column"] in df_c.columns
            ):
                seen.add(key)
                result.append((
                    row["query_table"], row["candidate_table"],
                    row["query_column"], row["candidate_column"],
                ))
            if len(result) >= n:
                break
    return result


def prepare_toy_lake() -> None:
    """Build tests/fixtures/toy_lake/ with 10 curated tables.

    Composition:
        - 3 Wikidata scenarios × 2 roles (source/target) = 6 tables
        - 2 WebTable JOIN pairs                           = 4 tables
        Total: 10 tables with annotated JOIN / UNION relationships.
    """
    print("\n[toy_lake] Building 10-table toy data lake ...")
    out     = FIXTURES / "toy_lake"
    tbl_out = out / "tables"
    tbl_out.mkdir(parents=True, exist_ok=True)

    ground_truth: list[dict] = []
    name_to_id:   dict[str, str] = {}

    # ── Wikidata (6 tables: joinable/semjoinable/unionable × source/target) ──
    wiki_base = DATASETS / "sm" / "Wikidata" / "Musicians"

    for scenario, task_type, sm_scenario in _WIKI_SCENARIOS[:3]:
        folder    = wiki_base / f"Musicians_{scenario}"
        meta_file = folder / f"metadata_Musicians_{scenario}.json"

        # parse column descriptions
        col_descs: dict[str, dict[str, str]] = {}
        if meta_file.exists():
            with open(meta_file, encoding="utf-8") as fh:
                for entry in json.load(fh):
                    col_descs[entry["tableName"]] = {
                        c["name"]: c["attribute_desc"] for c in entry["columns"]
                    }

        for role in ("source", "target"):
            tbl_name = f"musicians_{scenario}_{role}"
            csv_path = folder / f"musicians_{scenario}_{role}.csv"
            df = _read_csv(csv_path)
            if df is None:
                print(f"  WARN: cannot read {csv_path.name}")
                continue
            df = df.head(_TOY_SAMPLE_ROWS)
            tid = _stable_id(f"toy|wikidata|{tbl_name}")
            name_to_id[tbl_name] = tid
            _save_table(
                df, tbl_out / tid, tid, tbl_name,
                tenant_id="benchmark",
                source="wikidata",
                col_descriptions=col_descs.get(tbl_name),
            )
            print(f"  ✓ {tbl_name}  ({len(df)} rows × {len(df.columns)} cols)")

        # build ground truth entry from mapping.json
        mapping_file = folder / f"musicians_{scenario}_mapping.json"
        if mapping_file.exists():
            with open(mapping_file, encoding="utf-8") as fh:
                mapping = json.load(fh)
            src_name = f"musicians_{scenario}_source"
            tgt_name = f"musicians_{scenario}_target"
            ground_truth.append({
                "task_type":        task_type,
                "scenario":         sm_scenario,
                "source_table_id":  name_to_id.get(src_name),
                "target_table_id":  name_to_id.get(tgt_name),
                "source_table_name": src_name,
                "target_table_name": tgt_name,
                "column_matches": [
                    {"source_column": m["source_column"],
                     "target_column": m["target_column"]}
                    for m in mapping["matches"]
                ],
            })

    # ── WebTable JOIN (4 tables: 2 clean pairs) ──
    wt_dir      = DATASETS / "dl" / "join" / "tables"
    clean_pairs = _pick_clean_webtable_pairs(n=2)
    added_wt:   set[str] = set()

    for q_tbl, c_tbl, q_col, c_col in clean_pairs:
        for fname in (q_tbl, c_tbl):
            if fname in added_wt:
                continue
            df = _read_csv(wt_dir / fname)
            if df is None:
                continue
            df = df.head(_TOY_SAMPLE_ROWS)
            tbl_name = fname.removesuffix(".csv")
            tid = _stable_id(f"toy|webtable|{tbl_name}")
            name_to_id[tbl_name] = tid
            added_wt.add(fname)
            _save_table(
                df, tbl_out / tid, tid, tbl_name,
                tenant_id="benchmark",
                source="webtable",
            )
            print(f"  ✓ {fname}  ({len(df)} rows × {len(df.columns)} cols)")

        q_name = q_tbl.removesuffix(".csv")
        c_name = c_tbl.removesuffix(".csv")
        ground_truth.append({
            "task_type":        "JOIN",
            "scenario":         "SSD",
            "source_table_id":  name_to_id.get(q_name),
            "target_table_id":  name_to_id.get(c_name),
            "source_table_name": q_name,
            "target_table_name": c_name,
            "column_matches": [
                {"source_column": q_col, "target_column": c_col}
            ],
        })

    with open(out / "ground_truth.json", "w", encoding="utf-8") as fh:
        json.dump({"ground_truth": ground_truth}, fh, indent=2, ensure_ascii=False)

    n_tables = sum(1 for p in tbl_out.iterdir() if p.is_dir())
    print(f"[toy_lake] Done: {n_tables} tables, {len(ground_truth)} gt pairs → {out.relative_to(REPO_ROOT)}")


# ── 2. Retrieval Bench ─────────────────────────────────────────────────────────

def _convert_pool(
    src_dir: Path,
    out_dir: Path,
    id_prefix: str,
    skip_existing: bool,
) -> dict[str, str]:
    """Convert a directory of CSV files to Parquet; return {filename: table_id}.

    Args:
        src_dir: Directory containing source CSV files.
        out_dir: Output directory for Parquet tables.
        id_prefix: Prefix for UUID5 seed (ensures uniqueness across tasks).
        skip_existing: If True, skip tables whose directory already exists.

    Returns:
        Mapping from original CSV filename to stable table_id.
    """
    files = sorted(src_dir.glob("*.csv"))
    total = len(files)
    name_to_id: dict[str, str] = {}
    errors = 0

    for i, csv_path in enumerate(files, 1):
        tbl_name = csv_path.stem
        tid = _stable_id(f"{id_prefix}|{tbl_name}")
        name_to_id[csv_path.name] = tid

        tbl_dir = out_dir / tid
        if skip_existing and (tbl_dir / "data.parquet").exists():
            continue

        df = _read_csv(csv_path)
        if df is None or df.empty:
            errors += 1
            continue

        try:
            _save_table(df, tbl_dir, tid, tbl_name, "benchmark", id_prefix)
        except Exception as exc:
            errors += 1
            print(f"  WARN [{i}/{total}] {csv_path.name}: {exc}")
            continue

        if i % 500 == 0 or i == total:
            print(f"  ... {i}/{total} converted  (errors so far: {errors})")

    return name_to_id


def prepare_retrieval_bench(skip_existing: bool = False) -> None:
    """Build tests/fixtures/retrieval_bench/ from WebTable-Noise.

    Converts all CSV tables to Parquet and writes unified
    queries.json + ground_truth.json for both join and union tasks.

    Args:
        skip_existing: Skip re-converting already-present Parquet tables.
    """
    for task in ("join", "union"):
        print(f"\n[retrieval_bench/{task}] Converting tables ...")
        src_base = DATASETS / "dl" / task
        out_base = FIXTURES / "retrieval_bench" / task
        tbl_out  = out_base / "tables"
        tbl_out.mkdir(parents=True, exist_ok=True)

        # convert pool
        name_to_id = _convert_pool(
            src_dir=src_base / "tables",
            out_dir=tbl_out,
            id_prefix=f"retrieval|{task}",
            skip_existing=skip_existing,
        )

        # ── queries.json ──
        query_file = src_base / f"webtable_{task}_query.csv"
        queries: list[dict] = []
        with open(query_file, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                entry: dict = {
                    "table_id":   name_to_id.get(row["query_table"]),
                    "table_name": row["query_table"].removesuffix(".csv"),
                }
                if task == "join":          # JOIN 有列字段，UNION 无
                    entry["query_column"] = row["query_column"]
                queries.append(entry)

        with open(out_base / "queries.json", "w", encoding="utf-8") as fh:
            json.dump({"task_type": task.upper(), "queries": queries},
                      fh, indent=2, ensure_ascii=False)

        # ── ground_truth.json ──
        gt_file = src_base / f"webtable_{task}_ground_truth.csv"
        pairs: list[dict] = []
        with open(gt_file, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                entry = {
                    "query_table_id":     name_to_id.get(row["query_table"]),
                    "candidate_table_id": name_to_id.get(row["candidate_table"]),
                    "query_table_name":     row["query_table"].removesuffix(".csv"),
                    "candidate_table_name": row["candidate_table"].removesuffix(".csv"),
                }
                if task == "join":
                    entry["query_column"]     = row["query_column"]
                    entry["candidate_column"] = row["candidate_column"]
                pairs.append(entry)

        with open(out_base / "ground_truth.json", "w", encoding="utf-8") as fh:
            json.dump({"task_type": task.upper(), "pairs": pairs},
                      fh, indent=2, ensure_ascii=False)

        n_tables = sum(1 for p in tbl_out.iterdir() if p.is_dir())
        print(
            f"[retrieval_bench/{task}] Done: "
            f"{n_tables} tables | {len(queries)} queries | {len(pairs)} gt pairs"
        )


# ── 3. Matcher Bench ───────────────────────────────────────────────────────────

def prepare_matcher_bench_wikidata() -> None:
    """Build tests/fixtures/matcher_bench/wikidata/ from Wikidata Musicians.

    Each of the 4 scenarios produces:
        source/{table_id}/data.parquet + manifest.json
        target/{table_id}/data.parquet + manifest.json
        ground_truth.json
    """
    print("\n[matcher_bench/wikidata] Converting Wikidata Musicians ...")
    wiki_base = DATASETS / "sm" / "Wikidata" / "Musicians"

    for scenario, task_type, sm_scenario in _WIKI_SCENARIOS:
        folder    = wiki_base / f"Musicians_{scenario}"
        out_base  = FIXTURES / "matcher_bench" / "wikidata" / scenario
        out_base.mkdir(parents=True, exist_ok=True)

        # column descriptions from metadata.json
        col_descs: dict[str, dict[str, str]] = {}
        meta_file = folder / f"metadata_Musicians_{scenario}.json"
        if meta_file.exists():
            with open(meta_file, encoding="utf-8") as fh:
                for entry in json.load(fh):
                    col_descs[entry["tableName"]] = {
                        c["name"]: c["attribute_desc"] for c in entry["columns"]
                    }

        role_ids: dict[str, str] = {}
        for role in ("source", "target"):
            tbl_name = f"musicians_{scenario}_{role}"
            csv_path = folder / f"musicians_{scenario}_{role}.csv"
            df = _read_csv(csv_path)
            if df is None:
                print(f"  WARN: cannot read {csv_path.name}")
                continue

            tid = _stable_id(f"matcher|wikidata|{tbl_name}")
            role_ids[role] = tid
            role_out = out_base / role / tid
            _save_table(
                df, role_out, tid, tbl_name,
                tenant_id="benchmark",
                source="wikidata",
                col_descriptions=col_descs.get(tbl_name),
            )
            print(f"  ✓ {scenario}/{role}  ({len(df)} rows × {len(df.columns)} cols)")

        # ground_truth.json from mapping.json
        mapping_file = folder / f"musicians_{scenario}_mapping.json"
        if mapping_file.exists():
            with open(mapping_file, encoding="utf-8") as fh:
                mapping = json.load(fh)
            gt = {
                "task_type":        task_type,
                "scenario":         sm_scenario,
                "source_table_id":  role_ids.get("source"),
                "target_table_id":  role_ids.get("target"),
                "source_table_name": f"musicians_{scenario}_source",
                "target_table_name": f"musicians_{scenario}_target",
                "column_matches": [
                    {"source_column": m["source_column"],
                     "target_column": m["target_column"]}
                    for m in mapping["matches"]
                ],
            }
            with open(out_base / "ground_truth.json", "w", encoding="utf-8") as fh:
                json.dump(gt, fh, indent=2, ensure_ascii=False)

    print("[matcher_bench/wikidata] Done")


def prepare_matcher_bench_mimic() -> None:
    """Build tests/fixtures/matcher_bench/mimic_omop/ from MIMIC-III → OMOP.

    MIMIC-III and OMOP are schema-only datasets (SMD scenario):
    no row data → no Parquet. Outputs:
        mimic_schema.json   list of virtual tables with column definitions
        omop_schema.json    same
        ground_truth.json   column-level mapping (SRC_ENT.SRC_ATT → TGT_ENT.TGT_ATT)
    """
    print("\n[matcher_bench/mimic_omop] Processing MIMIC-III → OMOP (SMD) ...")
    data_dir = DATASETS / "sm" / "MIMIC_2_OMOP-main" / "data"
    out_dir  = FIXTURES / "matcher_bench" / "mimic_omop"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _parse_schema(csv_path: Path) -> list[dict]:
        """Group schema CSV rows by TableName into virtual-table objects."""
        tables: dict[str, dict] = {}
        df = _read_csv(csv_path)
        if df is None:
            return []
        # strip BOM from column names
        df.columns = [c.lstrip("\ufeff").strip() for c in df.columns]

        for _, row in df.iterrows():
            tname = str(row.get("TableName", "")).strip()
            if not tname:
                continue
            if tname not in tables:
                tables[tname] = {
                    "table_name": tname,
                    "table_desc": str(row.get("TableDesc", "")).strip(),
                    "columns":    [],
                }
            col_entry: dict = {
                "ordinal":     len(tables[tname]["columns"]),
                "name":        str(row.get("ColumnName", "")).strip(),
                "type":        str(row.get("ColumnType", "str")).strip().lower(),
                "description": str(row.get("ColumnDesc", "")).strip() or None,
                "is_pk":       str(row.get("IsPK", "NO")).strip().upper() == "YES",
                "is_fk":       str(row.get("IsFK", "NO")).strip().upper() == "YES",
            }
            tables[tname]["columns"].append(col_entry)
        return list(tables.values())

    mimic_tables = _parse_schema(data_dir / "MIMIC_III_Schema.csv")
    omop_tables  = _parse_schema(data_dir / "OMOP_Schema.csv")

    with open(out_dir / "mimic_schema.json", "w", encoding="utf-8") as fh:
        json.dump(mimic_tables, fh, indent=2, ensure_ascii=False)
    with open(out_dir / "omop_schema.json", "w", encoding="utf-8") as fh:
        json.dump(omop_tables, fh, indent=2, ensure_ascii=False)

    # ground_truth.json from MIMIC_to_OMOP_Mapping.csv
    mapping_df = _read_csv(data_dir / "MIMIC_to_OMOP_Mapping.csv")
    pairs: list[dict] = []
    if mapping_df is not None:
        mapping_df.columns = [c.lstrip("\ufeff").strip() for c in mapping_df.columns]
        for _, row in mapping_df.iterrows():
            pairs.append({
                "source_table": str(row["SRC_ENT"]).strip(),
                "source_column": str(row["SRC_ATT"]).strip(),
                "target_table": str(row["TGT_ENT"]).strip(),
                "target_column": str(row["TGT_ATT"]).strip(),
            })

    gt = {
        "task_type": "MATCH_ONLY",
        "scenario":  "SMD",
        "note": "Schema-only: no Parquet files. Use mimic_schema.json / omop_schema.json as virtual table definitions.",
        "column_matches": pairs,
    }
    with open(out_dir / "ground_truth.json", "w", encoding="utf-8") as fh:
        json.dump(gt, fh, indent=2, ensure_ascii=False)

    print(
        f"[matcher_bench/mimic_omop] Done: "
        f"{len(mimic_tables)} MIMIC tables, {len(omop_tables)} OMOP tables, "
        f"{len(pairs)} column mappings"
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Prepare AdaCascade test fixtures from raw benchmark datasets."
    )
    parser.add_argument(
        "--only",
        choices=["toy", "retrieval", "matcher"],
        help="Run only one fixture set (default: all)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip Parquet tables that already exist (for incremental runs)",
    )
    args = parser.parse_args()

    # pre-flight checks
    if not DATASETS.exists():
        print(f"ERROR: datasets symlink not found at {DATASETS}")
        print("  Run: ln -s /root/autodl-tmp/Adac-dataset /root/AdaC/datasets")
        sys.exit(1)

    missing = []
    for p in [
        DATASETS / "dl" / "join" / "tables",
        DATASETS / "dl" / "union" / "tables",
        DATASETS / "sm" / "Wikidata",
        DATASETS / "sm" / "MIMIC_2_OMOP-main",
    ]:
        if not p.exists():
            missing.append(str(p))
    if missing:
        print("ERROR: missing dataset directories:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    only = args.only
    skip = args.skip_existing

    if only in (None, "toy"):
        prepare_toy_lake()
    if only in (None, "retrieval"):
        prepare_retrieval_bench(skip_existing=skip)
    if only in (None, "matcher"):
        prepare_matcher_bench_wikidata()
        prepare_matcher_bench_mimic()

    print("\nAll fixtures ready.")
    print(f"  Location: {FIXTURES.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
