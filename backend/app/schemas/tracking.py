"""Tracking schemas for lost quotes, completed projects, and insights."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, condecimal


class LostQuoteCreate(BaseModel):
    """Record a lost quote."""

    quote_id: UUID
    winning_price: condecimal(gt=0, decimal_places=2)
    competitor: str | None = Field(None, max_length=255)
    loss_reason: str = Field(..., max_length=255)
    notes: str | None = None


class LostQuoteRead(BaseModel):
    """Lost quote record."""

    id: int
    quote_id: UUID
    original_price: Decimal
    winning_price: Decimal
    competitor: str | None
    loss_reason: str
    notes: str | None
    recorded_by_id: UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


class CompletedProjectCreate(BaseModel):
    """Record a completed project."""

    project_id: UUID
    quote_id: UUID
    quoted_cost: condecimal(gt=0, decimal_places=2)
    actual_material: condecimal(ge=0, decimal_places=2)
    actual_labor: condecimal(ge=0, decimal_places=2)
    actual_overhead: condecimal(ge=0, decimal_places=2)
    actual_total: condecimal(gt=0, decimal_places=2)
    final_price: condecimal(gt=0, decimal_places=2)
    customer_satisfaction: int | None = Field(None, ge=1, le=5)
    lessons_learned: str | None = None


class CompletedProjectRead(BaseModel):
    """Completed project record."""

    id: int
    project_id: UUID
    quote_id: UUID
    quoted_cost: Decimal
    actual_material: Decimal
    actual_labor: Decimal
    actual_overhead: Decimal
    actual_total: Decimal
    final_price: Decimal
    margin_achieved_pct: Decimal
    customer_satisfaction: int | None
    lessons_learned: str | None
    recorded_by_id: UUID
    completed_at: datetime

    model_config = {"from_attributes": True}


class InsightsRead(BaseModel):
    """Aggregated insights from lost quotes and completed projects."""

    lost_quotes_count: int
    avg_price_gap_pct: Decimal | None
    top_loss_reasons: list[dict[str, int]]
    completed_projects_count: int
    avg_margin_achieved_pct: Decimal | None
    avg_cost_variance_pct: Decimal | None
