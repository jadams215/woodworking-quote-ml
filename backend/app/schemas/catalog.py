"""Catalog schemas for material costs, labor rates, and price books."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, condecimal


class MaterialCostRead(BaseModel):
    """Material cost entry."""

    id: UUID
    wood_species: str
    grade: str
    cost_per_bf: Decimal
    effective_from: date
    effective_to: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MaterialCostUpdate(BaseModel):
    """Update material cost (creates new effective-dated row)."""

    cost_per_bf: condecimal(gt=0, decimal_places=4)


class LaborRateRead(BaseModel):
    """Labor rate entry."""

    id: UUID
    department: str
    hourly_rate: Decimal
    effective_from: date
    effective_to: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LaborRateUpdate(BaseModel):
    """Update labor rate (creates new effective-dated row)."""

    hourly_rate: condecimal(gt=0, decimal_places=2)


class PriceBookRead(BaseModel):
    """Price book snapshot summary."""

    id: UUID
    sha256_hash: str
    created_at: datetime
    created_by: UUID | None

    model_config = {"from_attributes": True}
