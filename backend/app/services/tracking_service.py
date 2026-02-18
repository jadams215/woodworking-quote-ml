"""Tracking service for lost quotes, completed projects, and insights."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.quote import Quote
from app.models.tracking import CompletedProject, LostQuote
from app.models.user import User
from app.schemas.tracking import CompletedProjectCreate, LostQuoteCreate


def record_lost_quote(db: Session, data: LostQuoteCreate, user: User) -> LostQuote:
    """
    Record a lost quote with competitor pricing.

    Args:
        db: Database session
        data: Lost quote data
        user: User recording the loss

    Returns:
        Created LostQuote instance

    Raises:
        ValueError: If quote not found
    """
    # Validate quote exists
    quote = db.query(Quote).filter(Quote.id == data.quote_id).first()
    if not quote:
        raise ValueError(f"Quote {data.quote_id} not found")

    lost_quote = LostQuote(
        quote_id=data.quote_id,
        original_price=quote.total_price,
        winning_price=data.winning_price,
        competitor=data.competitor,
        loss_reason=data.loss_reason,
        notes=data.notes,
        recorded_by_id=user.id,
    )
    db.add(lost_quote)
    db.flush()
    return lost_quote


def get_lost_quote_insights(db: Session) -> dict:
    """
    Get aggregated insights from lost quotes.

    Args:
        db: Database session

    Returns:
        Dictionary with insights (count, avg price gap, top loss reasons)
    """
    count = db.query(func.count(LostQuote.id)).scalar()

    # Average price gap percentage
    avg_gap = None
    if count > 0:
        gaps = db.query(
            ((LostQuote.original_price - LostQuote.winning_price) / LostQuote.original_price * 100)
        ).all()
        if gaps:
            avg_gap = sum(g[0] for g in gaps if g[0] is not None) / len(gaps)

    # Top loss reasons
    loss_reasons = (
        db.query(LostQuote.loss_reason, func.count(LostQuote.id))
        .group_by(LostQuote.loss_reason)
        .order_by(func.count(LostQuote.id).desc())
        .limit(5)
        .all()
    )
    top_reasons = [{"reason": reason, "count": count} for reason, count in loss_reasons]

    return {
        "lost_quotes_count": count,
        "avg_price_gap_pct": Decimal(str(avg_gap)) if avg_gap else None,
        "top_loss_reasons": top_reasons,
    }


def record_completed_project(
    db: Session, data: CompletedProjectCreate, user: User
) -> CompletedProject:
    """
    Record a completed project with actual costs vs. quoted.

    Args:
        db: Database session
        data: Completed project data
        user: User recording the completion

    Returns:
        Created CompletedProject instance

    Raises:
        ValueError: If project or quote not found
    """
    # Validate quote exists
    quote = db.query(Quote).filter(Quote.id == data.quote_id).first()
    if not quote:
        raise ValueError(f"Quote {data.quote_id} not found")

    # Calculate margin achieved
    margin_achieved = Decimal("0")
    if data.final_price > 0:
        margin_achieved = (
            (data.final_price - data.actual_total) / data.final_price * Decimal("100")
        )

    completed = CompletedProject(
        project_id=data.project_id,
        quote_id=data.quote_id,
        quoted_cost=data.quoted_cost,
        actual_material=data.actual_material,
        actual_labor=data.actual_labor,
        actual_overhead=data.actual_overhead,
        actual_total=data.actual_total,
        final_price=data.final_price,
        margin_achieved_pct=margin_achieved,
        customer_satisfaction=data.customer_satisfaction,
        lessons_learned=data.lessons_learned,
        recorded_by_id=user.id,
    )
    db.add(completed)
    db.flush()
    return completed


def get_project_insights(db: Session) -> dict:
    """
    Get aggregated insights from completed projects.

    Args:
        db: Database session

    Returns:
        Dictionary with insights (count, avg margin, avg cost variance)
    """
    count = db.query(func.count(CompletedProject.id)).scalar()

    # Average margin achieved
    avg_margin = None
    if count > 0:
        margins = db.query(CompletedProject.margin_achieved_pct).all()
        if margins:
            avg_margin = sum(m[0] for m in margins if m[0] is not None) / len(margins)

    # Average cost variance percentage
    avg_variance = None
    if count > 0:
        variances = db.query(
            ((CompletedProject.actual_total - CompletedProject.quoted_cost)
             / CompletedProject.quoted_cost * 100)
        ).all()
        if variances:
            avg_variance = sum(v[0] for v in variances if v[0] is not None) / len(variances)

    return {
        "completed_projects_count": count,
        "avg_margin_achieved_pct": Decimal(str(avg_margin)) if avg_margin else None,
        "avg_cost_variance_pct": Decimal(str(avg_variance)) if avg_variance else None,
    }
