from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


def _load_module(script_name: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.removesuffix(".py"), path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agri_demo_generator_creates_expected_lake(tmp_path: Path) -> None:
    generator = _load_module("generate_agri_demo.py")

    output_dir = tmp_path / "agri_lake"
    summary = generator.generate_all(output_dir)

    csv_paths = sorted(output_dir.glob("*/*.csv"))
    assert len(csv_paths) == 50
    assert len(summary) == 50
    assert (output_dir / "README.md").exists()

    expected_counts = {
        "farm_land": 8,
        "crop_production": 8,
        "livestock": 7,
        "supply_chain": 8,
        "personnel": 6,
        "finance": 7,
        "research": 6,
    }
    for domain, count in expected_counts.items():
        assert len(list((output_dir / domain).glob("*.csv"))) == count

    for csv_path in csv_paths:
        frame = pd.read_csv(csv_path)
        assert 10 <= len(frame) <= 20
        assert 6 <= len(frame.columns) <= 12
        assert all(column.strip() == column and column for column in frame.columns)

    farmers = pd.read_csv(output_dir / "personnel" / "farmers.csv")
    farm_workers = pd.read_csv(output_dir / "personnel" / "farm_workers.csv")
    assert list(farmers.columns) == [
        "farmer_id",
        "full_name",
        "contact_phone",
        "region_code",
        "farm_size_ha",
        "years_of_experience",
    ]
    assert list(farm_workers.columns) == [
        "worker_id",
        "name",
        "phone_number",
        "district_code",
        "plot_area_acres",
        "experience_years",
    ]
    assert farmers["farmer_id"].str.startswith("PERSON-").all()
    assert farm_workers["worker_id"].str.startswith("PERSON-").all()
    assert farmers["full_name"].tolist() == farm_workers["name"].head(len(farmers)).tolist()
    assert farmers["contact_phone"].tolist() == farm_workers["phone_number"].head(len(farmers)).tolist()

    readme = (output_dir / "README.md").read_text(encoding="utf-8")
    assert "Scenario A - Discover" in readme
    assert "research_projects" in readme
    assert "field_trials" in readme
    assert "Scenario B - Match" in readme
    assert "farmer_id ↔ worker_id" in readme
    assert "Scenario C - Integrate" in readme
    assert "livestock_herds" in readme


def test_agri_demo_scenario_tables_share_demo_semantic_anchors(tmp_path: Path) -> None:
    generator = _load_module("generate_agri_demo.py")

    output_dir = tmp_path / "agri_lake"
    generator.generate_all(output_dir)

    discover_tables = {
        "research/research_projects.csv": {"research_project_id", "research_program", "trial_network", "funding_program"},
        "research/field_trials.csv": {"research_project_id", "research_program", "trial_network", "field_experiment"},
        "research/experiment_results.csv": {"research_project_id", "trial_id", "field_experiment", "research_outcome"},
        "finance/subsidies.csv": {"research_project_id", "research_program", "funding_program", "trial_network"},
        "finance/budgets.csv": {"research_project_id", "research_program", "funding_program", "trial_network"},
        "farm_land/farms.csv": {"research_project_id", "research_program", "trial_network", "adaptive_irrigation_research_key"},
    }
    for relative_path, expected_columns in discover_tables.items():
        frame = pd.read_csv(output_dir / relative_path)
        assert expected_columns.issubset(frame.columns)
        joined_values = " ".join(frame.astype(str).to_numpy().ravel()).lower()
        assert "adaptive irrigation research" in joined_values

    livestock_tables = {
        "livestock/livestock_herds.csv": {"herd_id", "animal_id", "livestock_program", "animal_care_plan", "herd_management_goal"},
        "livestock/animal_records.csv": {"animal_id", "herd_id", "livestock_program", "animal_care_plan", "herd_management_goal"},
        "livestock/veterinary_visits.csv": {"animal_id", "herd_id", "livestock_program", "animal_care_plan", "herd_management_goal"},
        "livestock/feed_inventory.csv": {"animal_id", "herd_id", "livestock_program", "feed_program", "animal_care_plan"},
        "livestock/milk_production.csv": {"animal_id", "herd_id", "livestock_program", "milk_quality_program", "animal_care_plan"},
    }
    for relative_path, expected_columns in livestock_tables.items():
        frame = pd.read_csv(output_dir / relative_path)
        assert expected_columns.issubset(frame.columns)
        joined_values = " ".join(frame.astype(str).to_numpy().ravel()).lower()
        assert "dairy herd health" in joined_values


def test_agri_demo_discover_tables_share_column_name_anchor(tmp_path: Path) -> None:
    generator = _load_module("generate_agri_demo.py")

    output_dir = tmp_path / "agri_lake"
    generator.generate_all(output_dir)

    for relative_path in [
        "research/research_projects.csv",
        "research/field_trials.csv",
        "research/experiment_results.csv",
        "finance/subsidies.csv",
        "finance/budgets.csv",
        "farm_land/farms.csv",
    ]:
        frame = pd.read_csv(output_dir / relative_path)
        assert "adaptive_irrigation_research_key" in frame.columns
        assert "research_project_registry" in frame.columns


def test_agri_demo_match_tables_contain_synonym_anchors(tmp_path: Path) -> None:
    generator = _load_module("generate_agri_demo.py")

    output_dir = tmp_path / "agri_lake"
    generator.generate_all(output_dir)

    farmers = pd.read_csv(output_dir / "personnel" / "farmers.csv")
    farm_workers = pd.read_csv(output_dir / "personnel" / "farm_workers.csv")
    farmers_text = " ".join(farmers.astype(str).to_numpy().ravel()).lower()
    workers_text = " ".join(farm_workers.astype(str).to_numpy().ravel()).lower()

    for anchor in [
        "person identity",
        "person name",
        "person phone",
        "person region",
        "person farm area",
        "person work experience",
    ]:
        assert anchor in farmers_text
        assert anchor in workers_text


def test_agri_demo_uploader_builds_dataset_upload_request(tmp_path: Path) -> None:
    uploader = _load_module("upload_agri_demo.py")
    csv_dir = tmp_path / "agri_lake" / "farm_land"
    csv_dir.mkdir(parents=True)
    csv_path = csv_dir / "farms.csv"
    csv_path.write_text("farm_id,farm_name\nFARM-001,Green Valley\n", encoding="utf-8")

    request = uploader.build_upload_request(
        root=tmp_path / "agri_lake",
        api_base_url="http://localhost:6008",
        tenant_id="demo",
        dataset_id="dataset-demo",
        uploaded_by="tester",
    )

    assert request.url == "http://localhost:6008/datasets/dataset-demo/tables"
    assert request.headers["Authorization"] == "Bearer dev-local-token"
    assert request.headers["X-Tenant-Id"] == "demo"
    assert request.data["uploaded_by"] == "tester"
    assert request.files[0][0] == "files"
    assert request.files[0][1][0] == "farms.csv"
