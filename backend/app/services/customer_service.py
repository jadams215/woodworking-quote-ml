"""Customer service for CRUD operations."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    """
    Create a new customer.

    Args:
        db: Database session
        data: Customer creation data

    Returns:
        Created Customer instance
    """
    customer = Customer(**data.model_dump())
    db.add(customer)
    db.flush()
    return customer


def get_customer(db: Session, customer_id: UUID) -> Customer | None:
    """
    Get customer by ID.

    Args:
        db: Database session
        customer_id: Customer UUID

    Returns:
        Customer if found, None otherwise
    """
    return db.query(Customer).filter(Customer.id == customer_id).first()


def list_customers(
    db: Session, skip: int = 0, limit: int = 100, active_only: bool = True
) -> list[Customer]:
    """
    List customers with pagination.

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        active_only: Filter to active customers only

    Returns:
        List of Customer instances
    """
    query = db.query(Customer)
    if active_only:
        query = query.filter(Customer.is_active == True)
    return query.offset(skip).limit(limit).all()


def update_customer(db: Session, customer_id: UUID, data: CustomerUpdate) -> Customer | None:
    """
    Update customer information.

    Args:
        db: Database session
        customer_id: Customer UUID
        data: Update data (only provided fields updated)

    Returns:
        Updated Customer if found, None otherwise
    """
    customer = get_customer(db, customer_id)
    if not customer:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(customer, key, value)

    db.flush()
    return customer


def delete_customer(db: Session, customer_id: UUID) -> bool:
    """
    Soft-delete a customer (set is_active=False).

    Args:
        db: Database session
        customer_id: Customer UUID

    Returns:
        True if deleted, False if not found
    """
    customer = get_customer(db, customer_id)
    if not customer:
        return False

    customer.is_active = False
    db.flush()
    return True
