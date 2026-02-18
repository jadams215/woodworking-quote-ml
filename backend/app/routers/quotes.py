"""Quote API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_estimator_or_admin
from app.database import get_db
from app.models.quote import QuoteStatus
from app.models.user import User
from app.schemas.quote import QuoteCreate, QuoteRead
from app.services.audit_service import log_action
from app.services.quote_service import create_quote, get_quote, list_quotes, reproduce_quote

router = APIRouter(prefix="/api/v2/quotes", tags=["Quotes"])


@router.post("", response_model=QuoteRead, status_code=status.HTTP_201_CREATED)
def create_quote_endpoint(
    data: QuoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Create a new quote by running the pure quoting engine.

    Computes material costs, labor, overhead, and generates 3 pricing tiers.
    """
    try:
        quote = create_quote(db, data, current_user)

        # Log quote creation
        log_action(
            db,
            user_id=current_user.id,
            action="create_quote",
            entity_type="quote",
            entity_id=str(quote.id),
            old_values=None,
            new_values={
                "quote_number": quote.quote_number,
                "customer_id": str(quote.customer_id),
                "total_price": str(quote.total_price),
            },
        )
        db.commit()

        return quote
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[QuoteRead])
def list_quotes_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    customer_id: UUID | None = Query(None),
    status: QuoteStatus | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List quotes with pagination and optional filters.

    Filter by customer ID and/or status.
    """
    return list_quotes(db, skip=skip, limit=limit, customer_id=customer_id, status=status)


@router.get("/{quote_id}", response_model=QuoteRead)
def get_quote_endpoint(
    quote_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get quote by ID with full details.

    Includes params, cost breakdown, and all pricing tiers.
    """
    quote = get_quote(db, quote_id)
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return quote


@router.post("/{quote_id}/reproduce")
def reproduce_quote_endpoint(
    quote_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_estimator_or_admin),
):
    """
    Reproduce a quote using its original snapshot and parameters.

    Validates reproducibility by comparing new result with stored values.
    Returns comparison showing if results match.
    """
    try:
        result = reproduce_quote(db, quote_id)

        # Log reproduction check
        log_action(
            db,
            user_id=current_user.id,
            action="reproduce_quote",
            entity_type="quote",
            entity_id=str(quote_id),
            old_values=None,
            new_values={"matches": result["matches"]},
        )
        db.commit()

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{quote_id}/pdf")
def get_quote_pdf_endpoint(
    quote_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate and download quote as PDF.

    Returns PDF binary with proper content-type header.
    """
    quote = get_quote(db, quote_id)
    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    # Import here to avoid loading PDF libraries on startup
    from app.pdf.generator import generate_quote_pdf

    try:
        pdf_bytes = generate_quote_pdf(quote)

        # Log PDF generation
        log_action(
            db,
            user_id=current_user.id,
            action="generate_pdf",
            entity_type="quote",
            entity_id=str(quote_id),
            old_values=None,
            new_values=None,
        )
        db.commit()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="quote_{quote.quote_number}.pdf"'
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}",
        )
