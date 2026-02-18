"""Catalog API endpoints for materials, labor rates, and price books."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.catalog import (
    LaborRateRead,
    LaborRateUpdate,
    MaterialCostRead,
    MaterialCostUpdate,
    PriceBookRead,
)
from app.services.audit_service import log_action
from app.services.catalog_service import (
    get_active_labor_rates,
    get_active_materials,
    update_material_cost,
)

router = APIRouter(prefix="/api/v2/catalog", tags=["Catalog"])


@router.get("/materials", response_model=list[MaterialCostRead])
def get_materials_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all active material costs.

    Returns currently effective material costs for all species/grade combinations.
    """
    return get_active_materials(db)


@router.put("/materials/{species}/{grade}", response_model=MaterialCostRead)
def update_material_cost_endpoint(
    species: str,
    grade: str,
    data: MaterialCostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update material cost (admin only).

    Creates new effective-dated row and closes previous one.
    Automatically creates new PriceBookSnapshot.
    """
    try:
        # Get old cost for audit
        old_costs = get_active_materials(db)
        old_cost = next(
            (m for m in old_costs if m.wood_species == species and m.grade == grade), None
        )
        old_value = str(old_cost.cost_per_bf) if old_cost else None

        # Update cost (creates new snapshot)
        new_cost = update_material_cost(db, species, grade, data, current_user.id)

        # Log update
        log_action(
            db,
            user_id=current_user.id,
            action="update_material_cost",
            entity_type="material_cost",
            entity_id=f"{species}/{grade}",
            old_values={"cost_per_bf": old_value},
            new_values={"cost_per_bf": str(data.cost_per_bf)},
        )
        db.commit()

        return new_cost
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/labor-rates", response_model=list[LaborRateRead])
def get_labor_rates_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all active labor rates.

    Returns currently effective labor rates for all departments.
    """
    return get_active_labor_rates(db)


@router.get("/snapshot/current", response_model=dict)
def get_current_snapshot_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the current price book snapshot.

    Returns the most recent snapshot with all pricing data.
    """
    from app.services.catalog_service import get_current_price_book

    try:
        price_book = get_current_price_book(db)
        return {
            "snapshot_hash": price_book.to_sha256(),
            "material_costs": price_book.material_costs,
            "labor_rates": price_book.labor_rates,
            "overhead_pct": str(price_book.overhead_pct),
            "grade_multipliers": price_book.grade_multipliers,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
