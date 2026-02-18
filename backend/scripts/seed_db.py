"""
Seed the database with initial cost data and admin user.

Reads config/cost_tables.json and creates:
- MaterialCost rows (one per species+grade combination)
- LaborRate rows (one per department)
- OverheadConfig row with all configuration
- Initial PriceBookSnapshot with SHA-256 hash
- Admin user account

Usage:
    python scripts/seed_db.py
"""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.database import SessionLocal, engine
from app.engine.snapshot import create_snapshot
from app.models import Base
from app.models.catalog import LaborRate, MaterialCost, OverheadConfig
from app.models.user import User, UserRole
from app.utils.decimal_utils import to_decimal


def load_cost_tables() -> dict:
    """Load cost data from config/cost_tables.json."""
    config_path = Path(__file__).parent.parent.parent / "config" / "cost_tables.json"
    with open(config_path) as f:
        return json.load(f)


def seed_material_costs(db: Session, cost_data: dict, effective_from: date) -> None:
    """Create MaterialCost rows for each species+grade combination."""
    species_costs = cost_data["material_costs_per_bf"]
    grade_multipliers = cost_data["grade_multipliers"]

    material_costs = []
    for species, base_cost in species_costs.items():
        for grade, multiplier in grade_multipliers.items():
            cost_per_bf = to_decimal(base_cost) * to_decimal(multiplier)
            material_cost = MaterialCost(
                id=uuid4(),
                wood_species=species,
                grade=grade,
                cost_per_bf=cost_per_bf,
                effective_from=effective_from,
                effective_to=None,  # Open-ended (current)
            )
            material_costs.append(material_cost)

    db.add_all(material_costs)
    print(f"* Created {len(material_costs)} MaterialCost rows")


def seed_labor_rates(db: Session, cost_data: dict, effective_from: date) -> None:
    """Create LaborRate rows for each department."""
    labor_rates_data = cost_data["labor_rates"]

    labor_rates = []
    for department, rate in labor_rates_data.items():
        labor_rate = LaborRate(
            id=uuid4(),
            department=department,
            hourly_rate=to_decimal(rate),
            effective_from=effective_from,
            effective_to=None,  # Open-ended (current)
        )
        labor_rates.append(labor_rate)

    db.add_all(labor_rates)
    print(f"* Created {len(labor_rates)} LaborRate rows")


def seed_overhead_config(db: Session, cost_data: dict, effective_from: date) -> None:
    """Create OverheadConfig row with all configuration."""
    # Convert all nested dicts to have Decimal values
    waste_factors = {k: str(to_decimal(v)) for k, v in cost_data["waste_factors"].items()}
    complexity_multipliers = {
        k: str(to_decimal(v)) for k, v in cost_data["complexity_multipliers"].items()
    }
    finishing_costs = {
        k: str(to_decimal(v)) for k, v in cost_data["finishing_costs_per_sqft"].items()
    }

    overhead_config = OverheadConfig(
        id=uuid4(),
        overhead_pct=to_decimal(cost_data["overhead_pct"]),
        waste_factors=waste_factors,
        complexity_multipliers=complexity_multipliers,
        finishing_costs_per_sqft=finishing_costs,
        delivery_base_fee=to_decimal(cost_data["delivery"]["base_fee"]),
        delivery_per_mile=to_decimal(cost_data["delivery"]["per_mile"]),
        delivery_heavy_surcharge=to_decimal(cost_data["delivery"]["heavy_item_surcharge"]),
        installation_multiplier=to_decimal(cost_data["installation_multiplier"]),
        powder_coating_per_sqft=to_decimal(cost_data["powder_coating_per_sqft"]),
        max_risk_adjustment_pct=to_decimal(cost_data["max_risk_adjustment_pct"]),
        effective_from=effective_from,
        effective_to=None,  # Open-ended (current)
    )

    db.add(overhead_config)
    print("* Created OverheadConfig")


def seed_admin_user(db: Session) -> User:
    """Create initial admin user."""
    # Check if admin already exists
    existing = db.query(User).filter(User.email == "admin@b10union.com").first()
    if existing:
        print(f"* Admin user already exists (id={existing.id})")
        return existing

    admin = User(
        email="admin@b10union.com",
        hashed_password=hash_password("admin123"),  # Change in production!
        full_name="System Administrator",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    print("* Created admin user (email: admin@b10union.com, password: admin123)")
    return admin


def create_initial_snapshot(db: Session, cost_data: dict, admin_user: User) -> None:
    """Create the initial PriceBookSnapshot."""
    # Build snapshot data matching PriceBook structure
    snapshot_data = {
        "material_costs": {},
        "labor_rates": {},
        "grade_multipliers": {k: str(to_decimal(v)) for k, v in cost_data["grade_multipliers"].items()},
        "overhead_pct": str(to_decimal(cost_data["overhead_pct"])),
        "waste_factors": {k: str(to_decimal(v)) for k, v in cost_data["waste_factors"].items()},
        "complexity_multipliers": {k: str(to_decimal(v)) for k, v in cost_data["complexity_multipliers"].items()},
        "finishing_costs_per_sqft": {k: str(to_decimal(v)) for k, v in cost_data["finishing_costs_per_sqft"].items()},
        "delivery_base_fee": str(to_decimal(cost_data["delivery"]["base_fee"])),
        "delivery_per_mile": str(to_decimal(cost_data["delivery"]["per_mile"])),
        "delivery_heavy_surcharge": str(to_decimal(cost_data["delivery"]["heavy_item_surcharge"])),
        "installation_multiplier": str(to_decimal(cost_data["installation_multiplier"])),
        "powder_coating_per_sqft": str(to_decimal(cost_data["powder_coating_per_sqft"])),
        "max_risk_adjustment_pct": str(to_decimal(cost_data["max_risk_adjustment_pct"])),
    }

    # Material costs: species -> {grade -> cost_per_bf}
    species_costs = cost_data["material_costs_per_bf"]
    grade_multipliers = cost_data["grade_multipliers"]
    for species, base_cost in species_costs.items():
        snapshot_data["material_costs"][species] = {}
        for grade, multiplier in grade_multipliers.items():
            cost_per_bf = to_decimal(base_cost) * to_decimal(multiplier)
            snapshot_data["material_costs"][species][grade] = str(cost_per_bf)

    # Labor rates: department -> hourly_rate
    for dept, rate in cost_data["labor_rates"].items():
        snapshot_data["labor_rates"][dept] = str(to_decimal(rate))

    # Create snapshot via service (handles SHA-256 hashing)
    snapshot = create_snapshot(db, snapshot_data, admin_user.id)
    print(f"* Created PriceBookSnapshot (hash: {snapshot.sha256_hash[:16]}...)")


def main():
    """Seed the database with initial data."""
    print("=== Seeding Database ===\n")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    # Load cost data
    cost_data = load_cost_tables()
    print(f"* Loaded cost data from config/cost_tables.json\n")

    # Effective date for all initial catalog entries
    effective_from = date(2024, 1, 1)

    db = SessionLocal()
    try:
        # Create admin user first (needed for snapshot created_by)
        admin_user = seed_admin_user(db)

        # Seed catalog tables
        seed_material_costs(db, cost_data, effective_from)
        seed_labor_rates(db, cost_data, effective_from)
        seed_overhead_config(db, cost_data, effective_from)

        # Create initial snapshot
        create_initial_snapshot(db, cost_data, admin_user)

        db.commit()
        print("\n=== Seeding Complete ===")
        print("\nYou can now log in with:")
        print("  Email:    admin@b10union.com")
        print("  Password: admin123")
        print("\nWARNING:  Change the admin password in production!")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: Error during seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
