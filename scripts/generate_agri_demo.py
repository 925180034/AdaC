#!/usr/bin/env python3
"""Generate a smart agriculture demo data lake as CSV files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DOMAINS: dict[str, list[str]] = {
    "farm_land": [
        "farms",
        "fields",
        "soil_samples",
        "land_leases",
        "irrigation_systems",
        "field_sensors",
        "crop_rotation_plans",
        "farm_equipment",
    ],
    "crop_production": [
        "crops",
        "crop_varieties",
        "planting_records",
        "harvest_records",
        "yield_statistics",
        "crop_diseases",
        "pesticide_applications",
        "growth_monitoring",
    ],
    "livestock": [
        "livestock_herds",
        "animal_records",
        "veterinary_visits",
        "feed_inventory",
        "breeding_records",
        "milk_production",
        "animal_health_events",
    ],
    "supply_chain": [
        "suppliers",
        "purchase_orders",
        "warehouses",
        "inventory_batches",
        "product_shipments",
        "quality_inspections",
        "cold_storage_logs",
        "transportation_records",
    ],
    "personnel": [
        "farmers",
        "farm_workers",
        "work_assignments",
        "training_records",
        "safety_incidents",
        "equipment_maintenance",
    ],
    "finance": [
        "budgets",
        "expense_records",
        "sales_transactions",
        "subsidies",
        "insurance_policies",
        "loan_records",
        "audit_logs",
    ],
    "research": [
        "research_projects",
        "field_trials",
        "experiment_results",
        "extension_agents",
        "weather_stations",
        "soil_nutrient_reports",
    ],
}

COLUMNS: dict[str, list[str]] = {
    "farms": ["farm_id", "farm_name", "region_code", "farm_size_ha", "primary_crop", "research_project_id", "research_program", "trial_network", "adaptive_irrigation_research_key", "research_project_registry"],
    "fields": ["field_id", "farm_id", "field_name", "area_ha", "soil_type", "slope_grade", "current_crop", "last_survey_date"],
    "soil_samples": ["sample_id", "field_id", "sample_date", "ph_level", "organic_matter_pct", "nitrogen_ppm", "phosphorus_ppm", "potassium_ppm", "moisture_pct"],
    "land_leases": ["lease_id", "farm_id", "lessor_name", "start_date", "end_date", "leased_area_ha", "annual_rent_usd", "contract_status"],
    "irrigation_systems": ["system_id", "field_id", "system_type", "water_source", "flow_rate_lpm", "coverage_area_ha", "installed_year", "maintenance_status"],
    "field_sensors": ["sensor_id", "field_id", "sensor_type", "installed_date", "battery_pct", "last_reading_value", "reading_unit", "signal_status"],
    "crop_rotation_plans": ["rotation_plan_id", "field_id", "season_year", "previous_crop", "planned_crop", "rotation_reason", "expected_yield_tons", "advisor_name"],
    "farm_equipment": ["equipment_id", "farm_id", "equipment_type", "model_name", "purchase_year", "engine_hours", "condition_status", "assigned_operator"],
    "crops": ["crop_id", "crop_name", "crop_family", "growth_duration_days", "optimal_soil", "water_need_level", "market_category", "storage_method"],
    "crop_varieties": ["variety_id", "crop_id", "variety_name", "maturity_days", "disease_resistance", "average_yield_tons_ha", "seed_supplier", "recommended_region"],
    "planting_records": ["planting_id", "field_id", "crop_id", "variety_id", "planting_date", "seed_rate_kg_ha", "planted_area_ha", "operator_name"],
    "harvest_records": ["harvest_id", "field_id", "crop_id", "harvest_date", "harvested_area_ha", "gross_yield_tons", "moisture_pct", "harvest_quality_grade"],
    "yield_statistics": ["yield_stat_id", "farm_id", "crop_id", "season_year", "average_yield_tons_ha", "regional_rank", "rainfall_mm", "yield_variance_pct"],
    "crop_diseases": ["disease_id", "crop_id", "disease_name", "symptom_summary", "severity_level", "first_detected_date", "affected_area_ha", "control_method"],
    "pesticide_applications": ["application_id", "field_id", "crop_id", "chemical_name", "application_date", "dosage_l_per_ha", "target_pest", "safety_interval_days"],
    "growth_monitoring": ["monitoring_id", "field_id", "crop_id", "observation_date", "plant_height_cm", "leaf_color_score", "canopy_cover_pct", "growth_stage", "stress_notes"],
    "livestock_herds": ["herd_id", "animal_id", "livestock_program", "animal_care_plan", "herd_management_goal", "herd_type", "breed_name", "animal_count", "housing_unit", "grazing_area_ha", "feed_program", "health_risk_level"],
    "animal_records": ["animal_id", "herd_id", "livestock_program", "animal_care_plan", "herd_management_goal", "tag_number", "species", "breed_name", "birth_date", "sex", "health_status"],
    "veterinary_visits": ["visit_id", "animal_id", "herd_id", "livestock_program", "animal_care_plan", "herd_management_goal", "visit_date", "veterinarian_name", "diagnosis", "treatment_plan"],
    "feed_inventory": ["feed_batch_id", "animal_id", "herd_id", "livestock_program", "feed_program", "animal_care_plan", "feed_type", "supplier_id", "quantity_kg", "protein_pct", "expiry_date"],
    "breeding_records": ["breeding_id", "animal_id", "herd_id", "breeding_date", "sire_tag", "pregnancy_status", "expected_birth_date", "breeding_method"],
    "milk_production": ["milk_record_id", "animal_id", "herd_id", "livestock_program", "milk_quality_program", "animal_care_plan", "collection_date", "liters_collected", "fat_pct", "protein_pct", "quality_grade"],
    "animal_health_events": ["health_event_id", "animal_id", "herd_id", "event_date", "event_type", "severity_level", "recovery_status", "notes"],
    "suppliers": ["supplier_id", "supplier_name", "supplier_type", "contact_person", "phone_number", "region_code", "reliability_score", "payment_terms"],
    "purchase_orders": ["purchase_order_id", "supplier_id", "order_date", "item_category", "item_description", "quantity", "unit_price_usd", "delivery_status"],
    "warehouses": ["warehouse_id", "warehouse_name", "region_code", "storage_type", "capacity_tons", "temperature_control", "manager_name", "occupancy_pct"],
    "inventory_batches": ["batch_id", "warehouse_id", "product_name", "source_farm_id", "received_date", "quantity_tons", "quality_grade", "expiry_date"],
    "product_shipments": ["shipment_id", "batch_id", "warehouse_id", "destination_city", "ship_date", "delivered_date", "quantity_tons", "shipment_status"],
    "quality_inspections": ["inspection_id", "batch_id", "inspection_date", "inspector_name", "moisture_pct", "defect_rate_pct", "quality_grade", "approval_status"],
    "cold_storage_logs": ["cold_log_id", "warehouse_id", "batch_id", "log_time", "temperature_c", "humidity_pct", "door_open_minutes", "alarm_status"],
    "transportation_records": ["transport_id", "shipment_id", "carrier_name", "vehicle_plate", "driver_name", "route_code", "fuel_used_liters", "arrival_status"],
    "farmers": ["farmer_id", "full_name", "contact_phone", "region_code", "farm_size_ha", "years_of_experience"],
    "farm_workers": ["worker_id", "name", "phone_number", "district_code", "plot_area_acres", "experience_years"],
    "work_assignments": ["assignment_id", "worker_id", "farm_id", "field_id", "task_type", "assignment_date", "hours_worked", "supervisor_name"],
    "training_records": ["training_id", "worker_id", "course_name", "training_date", "certification_status", "trainer_name", "score_pct", "expiry_date"],
    "safety_incidents": ["incident_id", "worker_id", "farm_id", "incident_date", "incident_type", "severity_level", "days_lost", "corrective_action"],
    "equipment_maintenance": ["maintenance_id", "equipment_id", "technician_name", "maintenance_date", "service_type", "parts_replaced", "cost_usd", "next_service_date"],
    "budgets": ["budget_id", "farm_id", "research_project_id", "research_program", "funding_program", "trial_network", "adaptive_irrigation_research_key", "research_project_registry", "planned_amount_usd", "approved_amount_usd", "spent_amount_usd", "approval_status"],
    "expense_records": ["expense_id", "farm_id", "expense_date", "expense_category", "vendor_name", "amount_usd", "payment_method", "receipt_status"],
    "sales_transactions": ["sale_id", "farm_id", "crop_id", "buyer_name", "sale_date", "quantity_tons", "unit_price_usd", "payment_status"],
    "subsidies": ["subsidy_id", "farm_id", "research_project_id", "research_program", "funding_program", "trial_network", "adaptive_irrigation_research_key", "research_project_registry", "approved_amount_usd", "disbursement_status", "compliance_status"],
    "insurance_policies": ["policy_id", "farm_id", "insurer_name", "coverage_type", "coverage_amount_usd", "premium_usd", "start_date", "end_date"],
    "loan_records": ["loan_id", "farm_id", "lender_name", "loan_purpose", "principal_usd", "interest_rate_pct", "start_date", "repayment_status"],
    "audit_logs": ["audit_id", "farm_id", "audit_date", "auditor_name", "audit_area", "risk_rating", "finding_count", "resolution_status"],
    "research_projects": ["research_project_id", "project_title", "lead_farm_id", "principal_investigator", "research_program", "trial_network", "funding_program", "adaptive_irrigation_research_key", "research_project_registry", "subsidy_program", "trial_crop"],
    "field_trials": ["trial_id", "research_project_id", "field_id", "research_program", "trial_network", "field_experiment", "adaptive_irrigation_research_key", "research_project_registry", "treatment_group", "measurement_plan", "trial_status"],
    "experiment_results": ["result_id", "research_project_id", "trial_id", "field_experiment", "research_outcome", "adaptive_irrigation_research_key", "research_project_registry", "yield_change_pct", "soil_health_score", "water_saving_pct"],
    "extension_agents": ["agent_id", "agent_name", "region_code", "specialty_area", "phone_number", "assigned_farms", "visit_frequency", "program_affiliation"],
    "weather_stations": ["station_id", "farm_id", "station_name", "latitude", "longitude", "install_date", "rainfall_mm", "temperature_c", "wind_speed_kmh"],
    "soil_nutrient_reports": ["report_id", "sample_id", "field_id", "report_date", "nitrogen_ppm", "phosphorus_ppm", "potassium_ppm", "recommendation", "lab_name"],
}

NAMES = ["Ava Chen", "Liam Brooks", "Maya Patel", "Noah Green", "Emma Rivera", "Olivia Stone", "Lucas Wright", "Sophia Lee", "Ethan Clark", "Isabella Hall", "Mason Young", "Mia Allen", "Logan Scott", "Amelia King", "James Baker", "Harper Hill", "Henry Adams", "Ella Nelson", "Jack Carter", "Grace Turner"]
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
CROPS = ["wheat", "corn", "soybean", "rice", "tomato", "lettuce", "potato", "barley"]
FARMS = ["Green Valley", "Riverbend", "Sunrise Acres", "Cedar Grove", "Blue Ridge", "Meadow Path", "Golden Field", "Willow Creek"]


def _date(month: int, day: int, year: int = 2026) -> str:
    return f"{year}-{month:02d}-{day:02d}"


def _money(base: int, index: int) -> int:
    return base + index * 137


def _value(table: str, column: str, index: int) -> Any:
    row = index + 1
    if column in {"farmer_id", "worker_id"}:
        return f"PERSON-{row:03d} person identity"
    if column.endswith("_id"):
        prefix = "".join(part[0] for part in column.removesuffix("_id").split("_"))
        return f"{prefix.upper()}-{row:03d}"
    if column in {"full_name", "name"}:
        return f"{NAMES[index % len(NAMES)]} person name"
    if column in {"owner_name", "operator_name", "advisor_name", "veterinarian_name", "inspector_name", "driver_name", "technician_name", "auditor_name", "agent_name", "principal_investigator", "trainer_name", "supervisor_name", "assigned_operator", "manager_name", "contact_person"}:
        return NAMES[index % len(NAMES)]
    if column in {"contact_phone", "phone_number"}:
        return f"+1-555-{2300 + index:04d} person phone"
    if column in {"region_code", "district_code"}:
        return f"{REGIONS[index % len(REGIONS)]} person region"
    if column in {"recommended_region", "route_code"}:
        return REGIONS[index % len(REGIONS)]
    if column == "farm_name":
        return f"{FARMS[index % len(FARMS)]} Farm {row}"
    if column in {"field_name", "station_name", "warehouse_name"}:
        return f"{column.removesuffix('_name').replace('_', ' ').title()} {row}"
    if column in {"crop_name", "current_crop", "previous_crop", "planned_crop", "primary_crop", "trial_crop", "product_name"}:
        return CROPS[index % len(CROPS)]
    if column in {"crop_family"}:
        return ["cereal", "legume", "nightshade", "brassica"][index % 4]
    if column in {"crop_id"}:
        return f"CROP-{(index % len(CROPS)) + 1:03d}"
    if column in {"farm_id", "lead_farm_id", "source_farm_id"}:
        return f"FARM-{(index % 8) + 1:03d}"
    if column in {"field_id"}:
        return f"FIELD-{(index % 12) + 1:03d}"
    if column in {"herd_id"}:
        return f"HERD-{(index % 7) + 1:03d}"
    if column in {"supplier_id"}:
        return f"SUP-{(index % 8) + 1:03d}"
    if column in {"worker_id"}:
        return f"WORKER-{(index % 12) + 1:03d}"
    if column in {"animal_id"}:
        return f"ANIMAL-{(index % 15) + 1:03d}"
    if column.endswith("_date") or column in {"start_date", "end_date", "expiry_date", "expected_birth_date", "next_service_date", "delivered_date", "ship_date", "log_time", "install_date", "installed_date", "last_survey_date", "first_detected_date"}:
        return _date((index % 12) + 1, (index % 27) + 1, 2025 + (index % 2))
    if column.endswith("_year") or column in {"installed_year", "purchase_year"}:
        return 2022 + (index % 5)
    if column.endswith("_pct") or column in {"ph_level", "interest_rate_pct", "fat_pct", "protein_pct", "moisture_pct", "organic_matter_pct", "distinct_ratio", "defect_rate_pct", "canopy_cover_pct", "yield_variance_pct", "water_saving_pct", "yield_change_pct"}:
        return round(4.5 + (index * 1.7) % 72, 2)
    if column in {"farm_size_ha", "plot_area_acres"}:
        return f"{round(3.5 + index * 2.4, 2)} person farm area"
    if column.endswith("_ha") or column in {"area_ha", "leased_area_ha", "coverage_area_ha", "planted_area_ha", "harvested_area_ha", "affected_area_ha", "grazing_area_ha"}:
        return round(3.5 + index * 2.4, 2)
    if column.endswith("_usd") or column in {"planned_amount_usd", "approved_amount_usd", "spent_amount_usd", "amount_usd", "unit_price_usd", "coverage_amount_usd", "premium_usd", "principal_usd", "annual_rent_usd", "medicine_cost_usd", "cost_usd"}:
        return _money(1200, index)
    if column.endswith("_kg") or column.endswith("_tons") or column.endswith("_liters") or column.endswith("_lpm") or column.endswith("_mm") or column.endswith("_ppm") or column.endswith("_cm") or column.endswith("_kmh") or column.endswith("_c"):
        return round(10 + index * 3.25, 2)
    if column in {"years_of_experience", "experience_years"}:
        return f"{1 + (index * 3) % 35} person work experience"
    if column in {"row_count", "animal_count", "quantity", "assigned_farms", "finding_count", "days_lost", "door_open_minutes", "safety_interval_days", "growth_duration_days", "maturity_days", "engine_hours", "hours_worked"}:
        return 1 + (index * 3) % 35
    if column in {"status", "contract_status", "maintenance_status", "signal_status", "delivery_status", "shipment_status", "approval_status", "certification_status", "payment_status", "disbursement_status", "compliance_status", "repayment_status", "resolution_status", "health_status", "recovery_status", "trial_status", "alarm_status", "pregnancy_status", "receipt_status", "current_status", "arrival_status"}:
        return ["active", "pending", "complete", "review", "stable"][index % 5]
    if column in {"quality_grade", "harvest_quality_grade"}:
        return ["A", "B", "Premium", "Standard"][index % 4]
    if column in {"severity_level", "health_risk_level", "water_need_level", "risk_rating"}:
        return ["low", "medium", "high"][index % 3]
    if column == "project_title":
        return ["Adaptive irrigation research trial", "Adaptive irrigation research subsidy", "Adaptive irrigation research soil study", "Adaptive irrigation research disease project", "Adaptive irrigation research fertilizer trial"][index % 5]
    if column in {"research_program", "trial_network", "funding_program", "field_experiment", "research_outcome", "demo_farm_role", "adaptive_irrigation_research_key", "research_project_registry"}:
        return f"adaptive irrigation research {column.replace('_', ' ')} {row}"
    if column in {"livestock_program", "animal_care_plan", "herd_management_goal", "milk_quality_program"}:
        return f"dairy herd health {column.replace('_', ' ')} {row}"
    if column in {"research_topic", "program_name", "subsidy_program", "specialty_area", "audit_area", "course_name", "task_type", "service_type", "coverage_type", "loan_purpose", "budget_category", "expense_category", "item_category", "supplier_type", "storage_type", "system_type", "sensor_type", "equipment_type", "event_type", "feed_type", "herd_type", "breed_name", "species", "breeding_method", "disease_name", "chemical_name", "target_pest", "growth_stage", "treatment_group", "measurement_plan", "recommendation", "rotation_reason", "control_method", "diagnosis", "treatment_plan", "symptom_summary", "stress_notes", "notes", "result_summary", "parts_replaced", "corrective_action", "item_description", "payment_terms", "market_category", "storage_method", "optimal_soil", "soil_type", "soil_zone", "water_source", "irrigation_type", "housing_unit", "feed_program", "cooling_tank_id", "vehicle_plate", "carrier_name", "buyer_name", "vendor_name", "insurer_name", "lender_name", "lab_name", "model_name"}:
        return f"{column.replace('_', ' ')} {row}"
    if column in {"latitude"}:
        return round(35.0 + index * 0.11, 5)
    if column in {"longitude"}:
        return round(-119.0 - index * 0.13, 5)
    return f"{table}_{column}_{row}"


def _frame(table: str, row_count: int) -> pd.DataFrame:
    return pd.DataFrame([{column: _value(table, column, index) for column in COLUMNS[table]} for index in range(row_count)])


def _write_table(out_dir: Path, domain: str, table: str, row_count: int) -> dict[str, Any]:
    domain_dir = out_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    frame = _frame(table, row_count)
    frame.to_csv(domain_dir / f"{table}.csv", index=False, encoding="utf-8")
    return {"domain": domain, "table": table, "rows": len(frame), "columns": list(frame.columns)}


def _generate_domain(out_dir: Path, domain: str, tables: list[str], offset: int) -> list[dict[str, Any]]:
    return [_write_table(out_dir, domain, table, 10 + ((offset + index) % 11)) for index, table in enumerate(tables)]


def generate_farm_land(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "farm_land", DOMAINS["farm_land"], 0)


def generate_crop_production(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "crop_production", DOMAINS["crop_production"], 3)


def generate_livestock(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "livestock", DOMAINS["livestock"], 6)


def generate_supply_chain(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "supply_chain", DOMAINS["supply_chain"], 9)


def generate_personnel(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "personnel", DOMAINS["personnel"], 2)


def generate_finance(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "finance", DOMAINS["finance"], 5)


def generate_research(out_dir: Path) -> list[dict[str, Any]]:
    return _generate_domain(out_dir, "research", DOMAINS["research"], 8)


def _write_readme(out_dir: Path, summary: list[dict[str, Any]]) -> None:
    lines = [
        "# Smart Agriculture Demo Data Lake",
        "",
        "This generated Dataset contains 50 semantic CSV tables for AdaCascade demonstrations.",
        "",
        "## Demonstration scenarios",
        "",
        "### Scenario A - Discover",
        "- Query table: `research_projects`",
        "- Expected discoveries: `field_trials`, `subsidies`, `experiment_results`, `farms`, `budgets`",
        "- Rationale: project titles, farm identifiers, budget/subsidy references, and trial result fields share research funding and field experiment semantics.",
        "",
        "### Scenario B - Match",
        "- Source table: `farmers`",
        "- Target table: `farm_workers`",
        "- Designed synonym column pairs:",
        "  - `farmer_id ↔ worker_id`",
        "  - `full_name ↔ name`",
        "  - `contact_phone ↔ phone_number`",
        "  - `region_code ↔ district_code`",
        "  - `farm_size_ha ↔ plot_area_acres`",
        "  - `years_of_experience ↔ experience_years`",
        "",
        "### Scenario C - Integrate",
        "- Query table: `livestock_herds`",
        "- Expected recommendations: `animal_records`, `veterinary_visits`, `feed_inventory`, `milk_production`",
        "- Rationale: herd IDs, animal health, feed, and milk collection fields connect livestock management workflows.",
        "",
        "## Tables",
        "",
    ]
    for item in summary:
        columns = ", ".join(f"`{column}`" for column in item["columns"])
        lines.append(f"- `{item['domain']}/{item['table']}.csv` — {item['rows']} rows × {len(item['columns'])} columns: {columns}")
    out_dir.joinpath("README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_all(out_dir: Path | str = Path("demo_data/agri_lake")) -> list[dict[str, Any]]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = [
        *generate_farm_land(output_dir),
        *generate_crop_production(output_dir),
        *generate_livestock(output_dir),
        *generate_supply_chain(output_dir),
        *generate_personnel(output_dir),
        *generate_finance(output_dir),
        *generate_research(output_dir),
    ]
    _write_readme(output_dir, summary)
    for item in summary:
        print(f"{item['domain']}/{item['table']}: {item['rows']}×{len(item['columns'])}")
    return summary


if __name__ == "__main__":
    generate_all()
