"""Quote service for creating, retrieving, and reproducing quotes."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.engine import generate_quote, get_or_create_current_snapshot, load_price_book
from app.engine.types import QuoteParams
from app.models.customer import Customer
from app.models.quote import Quote, QuoteStatus
from app.models.user import User
from app.schemas.quote import QuoteCreate
from app.utils.decimal_utils import round_money


def create_quote(db: Session, data: QuoteCreate, user: User) -> Quote:
    """
    Create a new quote by running the pure quoting engine.

    Args:
        db: Database session
        data: Quote creation parameters
        user: User creating the quote

    Returns:
        Created Quote instance with pricing tiers

    Raises:
        ValueError: If customer not found
    """
    # Validate customer exists
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise ValueError(f"Customer {data.customer_id} not found")

    # Get or create current price book snapshot
    snapshot = get_or_create_current_snapshot(db, user.id)

    # Load price book for pure engine
    price_book = load_price_book(db, snapshot.id)

    # Calculate board feet from dimensions
    board_feet = (
        data.length_in * data.width_in * data.height_in / Decimal("144")
    )  # Convert cubic inches to board feet

    # Build QuoteParams for pure engine
    params = QuoteParams(
        wood_species=data.wood_species,
        material_grade=data.material_grade,
        project_type=data.project_type or "custom",
        board_feet=board_feet,
        quantity=data.quantity,
        estimated_labor_hours=data.estimated_labor_hours,
        estimated_machine_hours=data.estimated_machine_hours,
        has_woodwork=data.has_woodwork,
        has_metalwork=data.has_metalwork,
        has_finishing=data.has_finishing,
        has_upholstery=data.has_upholstery,
        finishing_complexity=data.finishing_complexity,
        surface_area_sqft=data.surface_area_sqft,
        hardware_cost=data.hardware_cost,
        delivery_miles=data.delivery_miles,
        is_heavy_item=data.is_heavy_item,
        installation_required=data.installation_required,
        job_complexity_score=data.job_complexity_score,
        risk_adjustment_pct=data.risk_adjustment_pct,
    )

    # Generate quote number (simple incrementing format)
    last_quote = db.query(Quote).order_by(Quote.created_at.desc()).first()
    quote_number = f"Q-{(last_quote.id.int if last_quote else 0) + 1:06d}"

    # Run pure quoting engine
    timestamp = datetime.utcnow()
    result = generate_quote(params, price_book, quote_number, timestamp)

    # Create Quote ORM object from result
    quote = Quote(
        quote_number=quote_number,
        customer_id=data.customer_id,
        project_id=None,  # Not linked to project yet
        project_type=data.project_type,
        snapshot_id=snapshot.id,
        status=QuoteStatus.draft,
        params=params.to_dict(),
        cost_breakdown=result.breakdown.to_dict(),
        tier_low_price=round_money(result.tiers[0].price),
        tier_standard_price=round_money(result.tiers[1].price),
        tier_premium_price=round_money(result.tiers[2].price),
        selected_tier="standard",  # Default to standard tier
        total_cost=round_money(result.breakdown.total_cost),
        total_price=round_money(result.tiers[1].price),  # Standard tier price
        confidence_score=result.confidence_score,
        risk_flags=list(result.risk_flags),
        requires_review=len(result.risk_flags) > 0 or result.confidence_score < 70,
        notes=data.notes,
        created_by=user.id,
        expires_at=timestamp + timedelta(days=30),  # 30-day quote validity
    )

    db.add(quote)
    db.flush()
    return quote


def get_quote(db: Session, quote_id: UUID) -> Quote | None:
    """
    Get quote by ID with all relationships loaded.

    Args:
        db: Database session
        quote_id: Quote UUID

    Returns:
        Quote if found, None otherwise
    """
    return (
        db.query(Quote)
        .options(joinedload(Quote.customer), joinedload(Quote.snapshot))
        .filter(Quote.id == quote_id)
        .first()
    )


def list_quotes(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    customer_id: UUID | None = None,
    status: QuoteStatus | None = None,
) -> list[Quote]:
    """
    List quotes with pagination and optional filters.

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        customer_id: Filter by customer ID
        status: Filter by quote status

    Returns:
        List of Quote instances
    """
    query = db.query(Quote).options(joinedload(Quote.customer))

    if customer_id:
        query = query.filter(Quote.customer_id == customer_id)
    if status:
        query = query.filter(Quote.status == status)

    return query.order_by(Quote.created_at.desc()).offset(skip).limit(limit).all()


def reproduce_quote(db: Session, quote_id: UUID) -> dict:
    """
    Reproduce a quote using its original snapshot and parameters.

    Validates reproducibility by comparing new result with stored values.

    Args:
        db: Database session
        quote_id: Quote UUID to reproduce

    Returns:
        Dictionary with comparison results

    Raises:
        ValueError: If quote not found or snapshot missing
    """
    quote = get_quote(db, quote_id)
    if not quote:
        raise ValueError(f"Quote {quote_id} not found")

    # Load original price book snapshot
    price_book = load_price_book(db, quote.snapshot_id)

    # Reconstruct QuoteParams from stored params
    params = QuoteParams.from_dict(quote.params)

    # Re-run pure engine with original inputs
    result = generate_quote(params, price_book, quote.quote_number, quote.created_at)

    # Compare results
    original_cost = quote.total_cost
    reproduced_cost = round_money(result.breakdown.total_cost)
    matches = original_cost == reproduced_cost

    return {
        "quote_id": quote_id,
        "quote_number": quote.quote_number,
        "original_cost": original_cost,
        "reproduced_cost": reproduced_cost,
        "matches": matches,
        "snapshot_hash": result.snapshot_hash,
        "confidence_score": result.confidence_score,
        "risk_flags": list(result.risk_flags),
    }
