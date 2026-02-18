"""Seed market index data from the JSONL data pack and create multiplier rules.

Usage:
    cd backend
    python scripts/seed_market_data.py

This script:
1. Loads the JSONL data pack into market_index_series + observations
2. Creates multiplier_rules that map indexes to engine adjustments
3. Uses your current cost_tables.json values as baselines
"""

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import SessionLocal
from app.ingestion.jsonl_loader import load_jsonl_file
from app.models.market_index import (
    MarketIndexSeries,
    MultiplierRule,
)

# Path to data pack relative to repo root
DATA_PACK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "market_data_pack_2026_02.jsonl"
COST_TABLES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "cost_tables.json"


def load_cost_tables() -> dict:
    """Load current cost tables for baseline values."""
    if COST_TABLES_PATH.exists():
        with open(COST_TABLES_PATH) as f:
            return json.load(f)
    return {}


def create_multiplier_rules(db, cost_tables: dict) -> list[MultiplierRule]:
    """Create multiplier rules linking market series to engine adjustments."""
    rules_created = []
    today = date.today()

    # Map of (dataset, category, name_pattern) -> (domain, target_field, baseline)
    rule_defs = []

    # ---- Material rules ----
    # Walnut wholesale index -> adjusts your Walnut cost
    walnut_baseline = Decimal(str(cost_tables.get("material_costs_per_bf", {}).get("Walnut", "15.00")))
    walnut_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "lumber_price",
            MarketIndexSeries.category == "hardwood_wholesale",
            MarketIndexSeries.species == "Walnut",
        )
        .first()
    )
    if walnut_series:
        rule_defs.append((walnut_series.id, "material", "Walnut:FAS", walnut_baseline))

    # White Oak wholesale index
    oak_baseline = Decimal(str(cost_tables.get("material_costs_per_bf", {}).get("Oak", "8.00")))
    oak_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "lumber_price",
            MarketIndexSeries.category == "hardwood_wholesale",
            MarketIndexSeries.species == "White Oak",
        )
        .first()
    )
    if oak_series:
        rule_defs.append((oak_series.id, "material", "Oak:Standard", oak_baseline))

    # Hard Maple wholesale index
    maple_baseline = Decimal(str(cost_tables.get("material_costs_per_bf", {}).get("Maple", "9.00")))
    maple_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "lumber_price",
            MarketIndexSeries.category == "hardwood_wholesale",
            MarketIndexSeries.name.contains("Hard Maple"),
        )
        .first()
    )
    if maple_series:
        rule_defs.append((maple_series.id, "material", "Maple:Standard", maple_baseline))

    # ---- Labor rule ----
    # BLS cabinetmaker wage (national) -> adjusts all labor rates
    labor_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "labor_benchmark",
            MarketIndexSeries.name.contains("Cabinetmakers and bench carpenters"),
            MarketIndexSeries.name.contains("median_annual"),
        )
        .first()
    )
    if labor_series:
        # Baseline: current BLS median ($46,020/yr ÷ 2080 hrs ≈ $22.13/hr)
        # We use the annual wage as the tracking unit
        rule_defs.append((labor_series.id, "labor", "all_departments", Decimal("46020")))

    # ---- Fuel rule ----
    # EIA diesel -> adjusts delivery per-mile rate
    fuel_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "fuel_price_index",
        )
        .first()
    )
    if fuel_series:
        # Baseline: Jan 2026 diesel price
        rule_defs.append((fuel_series.id, "fuel", "delivery_per_mile", Decimal("3.624")))

    # ---- Demand rule ----
    # Dodge Momentum Index -> adjusts margin targets
    demand_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "construction_demand_signal",
        )
        .first()
    )
    if demand_series:
        # Baseline: Jan 2026 DMI
        rule_defs.append((demand_series.id, "demand", "margin_targets", Decimal("272.7")))

    # ---- Finishing rule ----
    # Powder coating benchmark -> adjusts powder coating per sqft
    pc_baseline = Decimal(str(cost_tables.get("powder_coating_per_sqft", "4.50")))
    pc_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "finish_cost_benchmark",
            MarketIndexSeries.name.contains("per_sqft_range"),
        )
        .first()
    )
    if pc_series:
        rule_defs.append((pc_series.id, "finishing", "powder_coating_per_sqft", pc_baseline))

    # ---- Subcontractor rule ----
    cnc_series = (
        db.query(MarketIndexSeries)
        .filter(
            MarketIndexSeries.dataset == "subcontractor_benchmark",
            MarketIndexSeries.name.contains("per_hour_range"),
        )
        .first()
    )
    if cnc_series:
        machine_rate = Decimal(str(cost_tables.get("labor_rates", {}).get("machine", "40.00")))
        rule_defs.append((cnc_series.id, "subcontractor", "machine_rate", machine_rate))

    # Create rules
    for series_id, domain, target_field, baseline in rule_defs:
        # Check if rule already exists
        existing = (
            db.query(MultiplierRule)
            .filter(
                MultiplierRule.series_id == series_id,
                MultiplierRule.domain == domain,
                MultiplierRule.target_field == target_field,
            )
            .first()
        )
        if existing:
            print(f"  Rule already exists: {domain}/{target_field}")
            continue

        rule = MultiplierRule(
            id=uuid4(),
            series_id=series_id,
            domain=domain,
            target_field=target_field,
            formula="ratio",
            baseline_value=baseline,
            baseline_date=today,
            floor_mult=Decimal("0.500000"),
            ceiling_mult=Decimal("3.000000"),
        )
        db.add(rule)
        rules_created.append(rule)
        print(f"  Created rule: {domain}/{target_field} (baseline={baseline})")

    db.flush()
    return rules_created


def main() -> None:
    print("=" * 60)
    print("Seeding Market Index Data")
    print("=" * 60)

    if not DATA_PACK_PATH.exists():
        print(f"ERROR: Data pack not found at {DATA_PACK_PATH}")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Step 1: Load JSONL data pack
        print(f"\n1. Loading data pack from {DATA_PACK_PATH.name}...")
        stats = load_jsonl_file(db, DATA_PACK_PATH, ingested_by="seed_market_data")
        print(f"   Lines read: {stats['lines_read']}")
        print(f"   Records parsed: {stats['records_parsed']}")
        print(f"   Series created: {stats['series_created']}")
        print(f"   Observations created: {stats['observations_created']}")
        print(f"   Observations skipped (duplicates): {stats['observations_skipped']}")
        if stats["errors"]:
            print(f"   Errors ({len(stats['errors'])}):")
            for err in stats["errors"][:10]:
                print(f"     - {err}")

        # Step 2: Create multiplier rules
        print("\n2. Creating multiplier rules...")
        cost_tables = load_cost_tables()
        rules = create_multiplier_rules(db, cost_tables)
        print(f"   Rules created: {len(rules)}")

        # Step 3: Verify
        series_count = db.query(MarketIndexSeries).count()
        from app.models.market_index import MarketIndexObservation
        obs_count = db.query(MarketIndexObservation).count()
        rule_count = db.query(MultiplierRule).count()

        print(f"\n3. Verification:")
        print(f"   Total series in DB: {series_count}")
        print(f"   Total observations in DB: {obs_count}")
        print(f"   Total multiplier rules in DB: {rule_count}")

        # Step 4: Compute current multipliers
        print("\n4. Current multiplier values:")
        from app.services.market_service import build_market_multipliers
        multipliers = build_market_multipliers(db)
        print(f"   Material multipliers: {dict(multipliers.material_multipliers)}")
        print(f"   Labor multiplier: {multipliers.labor_multiplier}")
        print(f"   Fuel surcharge factor: {multipliers.fuel_surcharge_factor}")
        print(f"   Demand premium factor: {multipliers.demand_premium_factor}")
        print(f"   Powder coating multiplier: {multipliers.powder_coating_multiplier}")
        print(f"   Snapshot hash: {multipliers.to_sha256()[:16]}...")

        db.commit()
        print("\nDone! Market data seeded successfully.")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
