"""
Seed the database with initial catalog data and price book from cost_tables.json.

Usage: cd backend && python scripts/seed_data.py
"""

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Add backend to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.catalog import WoodSpecies, MaterialGrade, LaborDepartment, FinishLevel
from app.models.price_book import (
    PriceBookVersion,
    MaterialPrice,
    LaborRate,
    FinishingRate,
    DeliveryRate,
    OverheadRate,
    ComplexityMultiplier,
)

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def load_cost_tables() -> dict:
    """Load cost_tables.json from the config directory."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "cost_tables.json"
    if not config_path.exists():
        print(f"ERROR: {config_path} not found")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def seed_users(db):
    """Create default admin user if not exists."""
    existing = db.query(User).filter(User.email == "admin@b10union.com").first()
    if existing:
        print("  Admin user already exists, skipping")
        return

    admin = User(
        email="admin@b10union.com",
        password_hash=pwd_context.hash("admin123"),
        full_name="Admin",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.flush()
    print("  Created admin user (admin@b10union.com / admin123)")


def seed_species(db, cost_tables: dict) -> dict[str, int]:
    """Seed wood species. Returns name->id mapping."""
    # Species from cost_tables + extras from Ben's data
    all_species = list(cost_tables["material_costs_per_bf"].keys()) + [
        "Ash", "Sapele", "White Oak", "Cedar", "Ambrosia Maple",
    ]
    seen = set()
    name_to_id = {}

    for name in all_species:
        if name in seen:
            continue
        seen.add(name)

        existing = db.query(WoodSpecies).filter(WoodSpecies.name == name).first()
        if existing:
            name_to_id[name] = existing.id
            continue

        species = WoodSpecies(name=name, is_active=True)
        db.add(species)
        db.flush()
        name_to_id[name] = species.id

    print(f"  Seeded {len(name_to_id)} wood species")
    return name_to_id


def seed_grades(db, cost_tables: dict) -> dict[str, int]:
    """Seed material grades. Returns name->id mapping."""
    grade_data = cost_tables["grade_multipliers"]
    waste_data = cost_tables["waste_factors"]
    name_to_id = {}

    for name, multiplier in grade_data.items():
        existing = db.query(MaterialGrade).filter(MaterialGrade.name == name).first()
        if existing:
            name_to_id[name] = existing.id
            continue

        waste = waste_data.get(name, 0.10)
        grade = MaterialGrade(
            name=name,
            multiplier=Decimal(str(multiplier)),
            waste_factor_pct=Decimal(str(waste)),
        )
        db.add(grade)
        db.flush()
        name_to_id[name] = grade.id

    print(f"  Seeded {len(name_to_id)} material grades")
    return name_to_id


def seed_departments(db, cost_tables: dict) -> dict[str, int]:
    """Seed labor departments. Returns name->id mapping."""
    name_to_id = {}
    for name in cost_tables["labor_rates"]:
        existing = db.query(LaborDepartment).filter(LaborDepartment.name == name).first()
        if existing:
            name_to_id[name] = existing.id
            continue

        dept = LaborDepartment(name=name)
        db.add(dept)
        db.flush()
        name_to_id[name] = dept.id

    print(f"  Seeded {len(name_to_id)} labor departments")
    return name_to_id


def seed_finish_levels(db, cost_tables: dict) -> dict[int, int]:
    """Seed finish levels. Returns level->id mapping."""
    level_names = {
        1: "Minimal",
        2: "Basic",
        3: "Moderate",
        4: "Complex",
        5: "Elaborate",
    }
    level_to_id = {}

    for level_str in cost_tables["finishing_costs_per_sqft"]:
        level = int(level_str)
        existing = db.query(FinishLevel).filter(FinishLevel.level == level).first()
        if existing:
            level_to_id[level] = existing.id
            continue

        fl = FinishLevel(level=level, name=level_names.get(level, f"Level {level}"))
        db.add(fl)
        db.flush()
        level_to_id[level] = fl.id

    print(f"  Seeded {len(level_to_id)} finish levels")
    return level_to_id


def seed_price_book(
    db,
    cost_tables: dict,
    species_map: dict[str, int],
    grade_map: dict[str, int],
    dept_map: dict[str, int],
    finish_map: dict[int, int],
):
    """Create a price book version and populate all rates."""
    # Check if a current version already exists
    existing = db.query(PriceBookVersion).filter(PriceBookVersion.is_current == True).first()
    if existing:
        print("  Price book version already exists, skipping")
        return

    # Create version
    version = PriceBookVersion(
        version_label="Initial-2024",
        effective_from=date(2024, 1, 1),
        is_current=True,
        notes="Seeded from cost_tables.json",
    )
    db.add(version)
    db.flush()

    # Material prices
    count = 0
    for species_name, cost_per_bf in cost_tables["material_costs_per_bf"].items():
        if species_name not in species_map:
            continue
        mp = MaterialPrice(
            version_id=version.id,
            species_id=species_map[species_name],
            price_per_bf=Decimal(str(cost_per_bf)),
        )
        db.add(mp)
        count += 1
    print(f"  Seeded {count} material prices")

    # Labor rates
    count = 0
    for dept_name, rate in cost_tables["labor_rates"].items():
        if dept_name not in dept_map:
            continue
        lr = LaborRate(
            version_id=version.id,
            department_id=dept_map[dept_name],
            rate_per_hour=Decimal(str(rate)),
        )
        db.add(lr)
        count += 1
    print(f"  Seeded {count} labor rates")

    # Finishing rates
    count = 0
    for level_str, rate in cost_tables["finishing_costs_per_sqft"].items():
        level = int(level_str)
        if level not in finish_map:
            continue
        fr = FinishingRate(
            version_id=version.id,
            finish_level_id=finish_map[level],
            rate_per_sqft=Decimal(str(rate)),
        )
        db.add(fr)
        count += 1
    print(f"  Seeded {count} finishing rates")

    # Delivery rates
    delivery = cost_tables["delivery"]
    dr = DeliveryRate(
        version_id=version.id,
        base_fee=Decimal(str(delivery["base_fee"])),
        per_mile=Decimal(str(delivery["per_mile"])),
        heavy_item_surcharge=Decimal(str(delivery["heavy_item_surcharge"])),
    )
    db.add(dr)
    print("  Seeded delivery rates")

    # Overhead rates
    oh = OverheadRate(
        version_id=version.id,
        overhead_pct=Decimal(str(cost_tables["overhead_pct"])),
        installation_multiplier=Decimal(str(cost_tables["installation_multiplier"])),
        max_risk_adjustment_pct=Decimal(str(cost_tables["max_risk_adjustment_pct"])),
        powder_coating_per_sqft=Decimal(str(cost_tables["powder_coating_per_sqft"])),
    )
    db.add(oh)
    print("  Seeded overhead rates")

    # Complexity multipliers
    count = 0
    for level_str, mult in cost_tables["complexity_multipliers"].items():
        cm = ComplexityMultiplier(
            version_id=version.id,
            complexity_level=int(level_str),
            multiplier=Decimal(str(mult)),
        )
        db.add(cm)
        count += 1
    print(f"  Seeded {count} complexity multipliers")

    print(f"  Price book version '{version.version_label}' created (id={version.id})")


def main():
    print("=== Seeding Woodworking Quote Database ===\n")

    cost_tables = load_cost_tables()
    print(f"Loaded cost_tables.json with {len(cost_tables)} sections\n")

    db = SessionLocal()
    try:
        print("[Users]")
        seed_users(db)

        print("\n[Catalog]")
        species_map = seed_species(db, cost_tables)
        grade_map = seed_grades(db, cost_tables)
        dept_map = seed_departments(db, cost_tables)
        finish_map = seed_finish_levels(db, cost_tables)

        print("\n[Price Book]")
        seed_price_book(db, cost_tables, species_map, grade_map, dept_map, finish_map)

        db.commit()
        print("\n=== Seed complete! ===")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
