"""
Database bridge for PriceBookSnapshot management.

This is the ONLY module in app.engine that imports SQLAlchemy.
All other engine modules are pure (no I/O, no side effects).
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.price_book import PriceBookSnapshot
from app.utils.decimal_utils import decimal_to_json_dict, json_dict_to_decimal

from .price_book import PriceBook


def create_snapshot(db: Session, cost_tables_dict: dict, user_id: uuid4) -> PriceBookSnapshot:
    """
    Create a new PriceBookSnapshot from cost tables dictionary.

    Args:
        db: Database session
        cost_tables_dict: Dictionary with material_costs, labor_rates, etc.
        user_id: ID of user creating the snapshot

    Returns:
        PriceBookSnapshot ORM object (not committed)
    """
    # Convert to PriceBook to compute SHA-256
    price_book = PriceBook.from_snapshot_data(cost_tables_dict)
    sha256_hash = price_book.to_sha256()

    # Check if snapshot with this hash already exists
    existing = db.query(PriceBookSnapshot).filter(
        PriceBookSnapshot.sha256_hash == sha256_hash
    ).first()
    if existing:
        return existing

    # Convert Decimals to strings for JSON storage
    json_data = decimal_to_json_dict(cost_tables_dict)

    snapshot = PriceBookSnapshot(
        id=uuid4(),
        sha256_hash=sha256_hash,
        data=json_data,
        created_by=user_id,
    )
    db.add(snapshot)
    db.flush()  # Get ID without committing
    return snapshot


def load_price_book(db: Session, snapshot_id: uuid4) -> PriceBook:
    """
    Load a PriceBook from a snapshot ID.

    Args:
        db: Database session
        snapshot_id: UUID of the snapshot

    Returns:
        PriceBook frozen dataclass (pure, no DB references)

    Raises:
        ValueError: If snapshot not found
    """
    snapshot = db.query(PriceBookSnapshot).filter(
        PriceBookSnapshot.id == snapshot_id
    ).first()
    if not snapshot:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    # Convert JSON strings back to Decimals
    data_with_decimals = json_dict_to_decimal(snapshot.data)
    return PriceBook.from_snapshot_data(data_with_decimals)


def get_or_create_current_snapshot(db: Session, user_id: uuid4) -> PriceBookSnapshot:
    """
    Get the current (most recent) snapshot, or create one from active catalog.

    Args:
        db: Database session
        user_id: ID of user (for created_by if creating new)

    Returns:
        PriceBookSnapshot ORM object

    Note:
        In production, you'd build cost_tables_dict by querying MaterialCost,
        LaborRate, OverheadConfig where effective_to IS NULL.
        For now, just return most recent snapshot.
    """
    # Get most recent snapshot
    latest = db.query(PriceBookSnapshot).order_by(
        PriceBookSnapshot.created_at.desc()
    ).first()

    if latest:
        return latest

    # If no snapshots exist, this is a problem - seed_db should have created one
    raise ValueError(
        "No price book snapshots found. Run scripts/seed_db.py to initialize."
    )
