"""Quote schemas for creation, reading, and listing."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, condecimal

from app.models.quote import QuoteStatus


class QuoteCreate(BaseModel):
    """Create a new quote."""

    customer_id: UUID
    project_name: str | None = None

    # Material parameters
    wood_species: str = Field(..., max_length=100)
    material_grade: str = Field(..., max_length=50)

    # Project classification
    project_type: str | None = Field(None, max_length=50, description="conference_table, credenza, built_in, coffee_table, custom")

    length_in: condecimal(gt=0, decimal_places=2) = Field(..., description="Length in inches")
    width_in: condecimal(gt=0, decimal_places=2) = Field(..., description="Width in inches")
    height_in: condecimal(gt=0, decimal_places=2) = Field(..., description="Height in inches")
    quantity: int = Field(..., gt=0)

    # Labor parameters
    estimated_labor_hours: condecimal(ge=0, decimal_places=2) = Field(Decimal("0"))
    estimated_machine_hours: condecimal(ge=0, decimal_places=2) = Field(Decimal("0"))

    # Work types
    has_woodwork: bool = True
    has_metalwork: bool = False
    has_finishing: bool = False
    has_upholstery: bool = False

    # Finishing parameters
    finishing_complexity: int = Field(1, ge=1, le=5)
    surface_area_sqft: condecimal(ge=0, decimal_places=2) | None = None

    # Hardware and delivery
    hardware_cost: condecimal(ge=0, decimal_places=2) = Field(Decimal("0"))
    delivery_miles: condecimal(ge=0, decimal_places=2) | None = None
    is_heavy_item: bool = False
    installation_required: bool = False

    # Risk and complexity
    job_complexity_score: int = Field(3, ge=1, le=5)
    risk_adjustment_pct: condecimal(ge=0, decimal_places=2) = Field(Decimal("0"))

    # Notes
    notes: str | None = None


class QuoteTierRead(BaseModel):
    """Single pricing tier."""

    name: str
    price: Decimal
    margin_pct: Decimal

    model_config = {"from_attributes": True}


class CostBreakdownRead(BaseModel):
    """Cost breakdown details."""

    material_cost: Decimal
    labor_cost: Decimal
    finishing_cost: Decimal
    hardware_cost: Decimal
    delivery_cost: Decimal
    overhead: Decimal
    risk_adjustment: Decimal
    total_cost: Decimal

    model_config = {"from_attributes": True}


class QuoteRead(BaseModel):
    """Full quote details."""

    id: UUID
    quote_number: str
    customer_id: UUID
    project_id: UUID | None
    status: QuoteStatus
    project_type: str | None

    # Pricing
    tier_low_price: Decimal
    tier_standard_price: Decimal
    tier_premium_price: Decimal
    selected_tier: str | None
    total_cost: Decimal
    total_price: Decimal

    # Analysis
    confidence_score: int
    risk_flags: list[str]
    requires_review: bool

    # Metadata
    snapshot_hash: str = Field(..., alias="snapshot_id")
    notes: str | None
    created_at: datetime
    updated_at: datetime | None
    locked_at: datetime | None
    expires_at: datetime | None

    # Full data (optional, for detail view)
    params: dict | None = None
    cost_breakdown: dict | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class QuoteListItem(BaseModel):
    """Abbreviated quote for list views."""

    id: UUID
    quote_number: str
    customer_id: UUID
    customer_name: str = Field(..., description="Joined from customer table")
    status: QuoteStatus
    total_price: Decimal
    confidence_score: int
    requires_review: bool
    created_at: datetime

    model_config = {"from_attributes": True}
