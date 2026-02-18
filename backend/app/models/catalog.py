"""Catalog models -- effective-dated material costs, labor rates, and overhead config.

All cost/rate tables use the effective-dating pattern:
    WHERE effective_from <= :as_of_date
      AND (effective_to IS NULL OR effective_to > :as_of_date)

effective_to = NULL means the row is the currently-active rate.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MaterialCost(Base):
    """Effective-dated cost per board-foot for a (species, grade) pair."""

    __tablename__ = "material_costs"
    __table_args__ = (
        UniqueConstraint(
            "wood_species", "grade", "effective_from",
            name="uq_material_cost_species_grade_from",
        ),
        Index(
            "ix_material_cost_species_grade_from",
            "wood_species", "grade", "effective_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wood_species: Mapped[str] = mapped_column(String(100), nullable=False)
    grade: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_per_bf: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<MaterialCost id={self.id} species={self.wood_species!r} "
            f"grade={self.grade!r} cost_per_bf={self.cost_per_bf}>"
        )


class LaborRate(Base):
    """Effective-dated hourly rate for a labor department."""

    __tablename__ = "labor_rates"
    __table_args__ = (
        UniqueConstraint(
            "department", "effective_from",
            name="uq_labor_rate_dept_from",
        ),
        Index(
            "ix_labor_rate_dept_from",
            "department", "effective_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<LaborRate id={self.id} department={self.department!r} "
            f"hourly_rate={self.hourly_rate}>"
        )


class OverheadConfig(Base):
    """Effective-dated overhead and miscellaneous cost configuration.

    JSONB fields store structured lookup tables:
      - waste_factors:             {"Economy": "0.15", "Standard": "0.10", "Premium": "0.08"}
      - complexity_multipliers:    {"1": "0.85", "2": "0.95", "3": "1.00", ...}
      - finishing_costs_per_sqft:  {"1": "1.50", "2": "3.00", ...}
    """

    __tablename__ = "overhead_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    overhead_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    waste_factors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    complexity_multipliers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    finishing_costs_per_sqft: Mapped[dict] = mapped_column(JSONB, nullable=False)
    delivery_base_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    delivery_per_mile: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    delivery_heavy_surcharge: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    installation_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    powder_coating_per_sqft: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    max_risk_adjustment_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<OverheadConfig id={self.id} overhead_pct={self.overhead_pct} "
            f"effective_from={self.effective_from}>"
        )
