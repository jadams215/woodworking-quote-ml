"""Customer API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin, require_estimator_or_admin
from app.database import get_db
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.services.audit_service import log_action
from app.services.customer_service import (
    create_customer,
    delete_customer,
    get_customer,
    list_customers,
    update_customer,
)

router = APIRouter(prefix="/api/v2/customers", tags=["Customers"])


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer_endpoint(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Create a new customer.

    Requires estimator or admin role.
    """
    customer = create_customer(db, data)

    # Log customer creation
    log_action(
        db,
        user_id=current_user.id,
        action="create_customer",
        entity_type="customer",
        entity_id=str(customer.id),
        old_values=None,
        new_values={"name": customer.name, "email": customer.email},
    )
    db.commit()

    return customer


@router.get("", response_model=list[CustomerRead])
def list_customers_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List customers with pagination.

    Filter by active status, ordered by name.
    """
    return list_customers(db, skip=skip, limit=limit, active_only=active_only)


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer_endpoint(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get customer by ID.

    Returns 404 if customer not found.
    """
    customer = get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer_endpoint(
    customer_id: UUID,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Update customer information.

    Only provided fields are updated. Requires estimator or admin role.
    """
    # Get old values for audit
    old_customer = get_customer(db, customer_id)
    if not old_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    old_values = {
        "name": old_customer.name,
        "email": old_customer.email,
        "phone": old_customer.phone,
        "is_active": old_customer.is_active,
    }

    # Update customer
    customer = update_customer(db, customer_id, data)

    # Log update
    log_action(
        db,
        user_id=current_user.id,
        action="update_customer",
        entity_type="customer",
        entity_id=str(customer_id),
        old_values=old_values,
        new_values=data.model_dump(exclude_unset=True),
    )
    db.commit()

    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_endpoint(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Soft-delete a customer (admin only).

    Sets is_active=False instead of deleting record.
    """
    success = delete_customer(db, customer_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Log deletion
    log_action(
        db,
        user_id=current_user.id,
        action="delete_customer",
        entity_type="customer",
        entity_id=str(customer_id),
        old_values={"is_active": True},
        new_values={"is_active": False},
    )
    db.commit()
