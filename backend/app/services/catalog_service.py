"""Catalog service for managing material costs, labor rates, and price books."""
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.engine import PriceBook, create_snapshot
from app.models.catalog import LaborRate, MaterialCost, OverheadConfig
from app.models.price_book import PriceBookSnapshot
from app.schemas.catalog import MaterialCostUpdate
from app.utils.decimal_utils import to_decimal


def get_active_materials(db: Session, as_of: date | None = None) -> list[MaterialCost]:
    """
    Get all active material costs as of a given date.

    Args:
        db: Database session
        as_of: Date to check (defaults to today)

    Returns:
        List of MaterialCost instances
    """
    if as_of is None:
        as_of = date.today()

    return (
        db.query(MaterialCost)
        .filter(
            MaterialCost.effective_from <= as_of,
            (MaterialCost.effective_to.is_(None)) | (MaterialCost.effective_to > as_of),
        )
        .order_by(MaterialCost.wood_species, MaterialCost.grade)
        .all()
    )


def get_active_labor_rates(db: Session, as_of: date | None = None) -> list[LaborRate]:
    """
    Get all active labor rates as of a given date.

    Args:
        db: Database session
        as_of: Date to check (defaults to today)

    Returns:
        List of LaborRate instances
    """
    if as_of is None:
        as_of = date.today()

    return (
        db.query(LaborRate)
        .filter(
            LaborRate.effective_from <= as_of,
            (LaborRate.effective_to.is_(None)) | (LaborRate.effective_to > as_of),
        )
        .order_by(LaborRate.department)
        .all()
    )


def update_material_cost(
    db: Session, species: str, grade: str, new_cost: MaterialCostUpdate, user_id: UUID
) -> MaterialCost:
    """
    Update material cost by creating new effective-dated row.

    Closes existing row and creates new one with today's effective_from.

    Args:
        db: Database session
        species: Wood species name
        grade: Material grade
        new_cost: New cost data
        user_id: User making the update

    Returns:
        New MaterialCost instance

    Raises:
        ValueError: If no active material cost found
    """
    today = date.today()

    # Find current active cost
    current = (
        db.query(MaterialCost)
        .filter(
            MaterialCost.wood_species == species,
            MaterialCost.grade == grade,
            MaterialCost.effective_to.is_(None),
        )
        .first()
    )

    if not current:
        raise ValueError(f"No active material cost for {species}/{grade}")

    # Close current row (set effective_to to yesterday)
    current.effective_to = today

    # Create new row with new cost
    new_row = MaterialCost(
        id=uuid4(),
        wood_species=species,
        grade=grade,
        cost_per_bf=new_cost.cost_per_bf,
        effective_from=today,
        effective_to=None,
    )
    db.add(new_row)
    db.flush()

    # Create new snapshot with updated costs
    _create_snapshot_from_catalog(db, user_id)

    return new_row


def get_current_price_book(db: Session) -> PriceBook:
    """
    Get the current (most recent) price book as PriceBook dataclass.

    Args:
        db: Database session

    Returns:
        PriceBook frozen dataclass

    Raises:
        ValueError: If no snapshots found
    """
    from app.engine.snapshot import load_price_book

    latest = db.query(PriceBookSnapshot).order_by(PriceBookSnapshot.created_at.desc()).first()
    if not latest:
        raise ValueError("No price book snapshots found")

    return load_price_book(db, latest.id)


def _create_snapshot_from_catalog(db: Session, user_id: UUID) -> PriceBookSnapshot:
    """
    Create a new snapshot by reading current catalog tables.

    Internal helper for updating catalog entries.

    Args:
        db: Database session
        user_id: User creating the snapshot

    Returns:
        New PriceBookSnapshot
    """
    today = date.today()

    # Build snapshot data from active catalog
    snapshot_data = {
        "material_costs": {},
        "labor_rates": {},
        "grade_multipliers": {},
        "overhead_pct": "",
        "waste_factors": {},
        "complexity_multipliers": {},
        "finishing_costs_per_sqft": {},
        "delivery_base_fee": "",
        "delivery_per_mile": "",
        "delivery_heavy_surcharge": "",
        "installation_multiplier": "",
        "powder_coating_per_sqft": "",
        "max_risk_adjustment_pct": "",
    }

    # Material costs
    materials = get_active_materials(db, today)
    for mat in materials:
        if mat.wood_species not in snapshot_data["material_costs"]:
            snapshot_data["material_costs"][mat.wood_species] = {}
        snapshot_data["material_costs"][mat.wood_species][mat.grade] = str(mat.cost_per_bf)

    # Labor rates
    labor_rates = get_active_labor_rates(db, today)
    for rate in labor_rates:
        snapshot_data["labor_rates"][rate.department] = str(rate.hourly_rate)

    # Overhead config (get most recent)
    overhead = (
        db.query(OverheadConfig)
        .filter(
            OverheadConfig.effective_from <= today,
            (OverheadConfig.effective_to.is_(None)) | (OverheadConfig.effective_to > today),
        )
        .first()
    )

    if overhead:
        snapshot_data["overhead_pct"] = str(overhead.overhead_pct)
        snapshot_data["waste_factors"] = overhead.waste_factors
        snapshot_data["complexity_multipliers"] = overhead.complexity_multipliers
        snapshot_data["finishing_costs_per_sqft"] = overhead.finishing_costs_per_sqft
        snapshot_data["delivery_base_fee"] = str(overhead.delivery_base_fee)
        snapshot_data["delivery_per_mile"] = str(overhead.delivery_per_mile)
        snapshot_data["delivery_heavy_surcharge"] = str(overhead.delivery_heavy_surcharge)
        snapshot_data["installation_multiplier"] = str(overhead.installation_multiplier)
        snapshot_data["powder_coating_per_sqft"] = str(overhead.powder_coating_per_sqft)
        snapshot_data["max_risk_adjustment_pct"] = str(overhead.max_risk_adjustment_pct)

    # Compute grade multipliers from material costs (ratio of grade cost to standard cost)
    # Simplification: use first species to derive multipliers
    if materials:
        species = materials[0].wood_species
        costs_by_grade = {
            mat.grade: mat.cost_per_bf for mat in materials if mat.wood_species == species
        }
        standard_cost = costs_by_grade.get("Standard", to_decimal("1"))
        for grade, cost in costs_by_grade.items():
            multiplier = cost / standard_cost if standard_cost > 0 else to_decimal("1")
            snapshot_data["grade_multipliers"][grade] = str(multiplier)

    return create_snapshot(db, snapshot_data, user_id)
