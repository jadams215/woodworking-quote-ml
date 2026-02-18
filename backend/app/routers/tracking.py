"""Tracking API endpoints for lost quotes and completed projects."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_estimator_or_admin
from app.database import get_db
from app.models.user import User
from app.schemas.tracking import (
    CompletedProjectCreate,
    CompletedProjectRead,
    InsightsRead,
    LostQuoteCreate,
    LostQuoteRead,
)
from app.services.audit_service import log_action
from app.services.tracking_service import (
    get_lost_quote_insights,
    get_project_insights,
    record_completed_project,
    record_lost_quote,
)

router = APIRouter(prefix="/api/v2/tracking", tags=["Tracking"])


@router.post("/lost-quotes", response_model=LostQuoteRead, status_code=status.HTTP_201_CREATED)
def record_lost_quote_endpoint(
    data: LostQuoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Record a lost quote with competitor pricing.

    Used to track why quotes are lost and price gaps.
    """
    try:
        lost_quote = record_lost_quote(db, data, current_user)

        # Log recording
        log_action(
            db,
            user_id=current_user.id,
            action="record_lost_quote",
            entity_type="lost_quote",
            entity_id=str(lost_quote.id),
            old_values=None,
            new_values={
                "quote_id": str(data.quote_id),
                "loss_reason": data.loss_reason,
            },
        )
        db.commit()

        return lost_quote
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/lost-quotes/insights", response_model=InsightsRead)
def get_lost_quotes_insights_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregated insights from lost quotes.

    Returns count, average price gap, and top loss reasons.
    """
    lost_insights = get_lost_quote_insights(db)
    project_insights = get_project_insights(db)

    return InsightsRead(
        lost_quotes_count=lost_insights["lost_quotes_count"],
        avg_price_gap_pct=lost_insights["avg_price_gap_pct"],
        top_loss_reasons=lost_insights["top_loss_reasons"],
        completed_projects_count=project_insights["completed_projects_count"],
        avg_margin_achieved_pct=project_insights["avg_margin_achieved_pct"],
        avg_cost_variance_pct=project_insights["avg_cost_variance_pct"],
    )


@router.post(
    "/completed-projects", response_model=CompletedProjectRead, status_code=status.HTTP_201_CREATED
)
def record_completed_project_endpoint(
    data: CompletedProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Record a completed project with actual vs. quoted costs.

    Used to track margin achievement and cost estimation accuracy.
    """
    try:
        completed = record_completed_project(db, data, current_user)

        # Log recording
        log_action(
            db,
            user_id=current_user.id,
            action="record_completed_project",
            entity_type="completed_project",
            entity_id=str(completed.id),
            old_values=None,
            new_values={
                "project_id": str(data.project_id),
                "margin_achieved_pct": str(completed.margin_achieved_pct),
            },
        )
        db.commit()

        return completed
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/project-insights", response_model=dict)
def get_project_insights_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregated insights from completed projects.

    Returns count, average margin achieved, and average cost variance.
    """
    return get_project_insights(db)
