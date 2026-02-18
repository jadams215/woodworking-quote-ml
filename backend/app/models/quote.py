"""Quote model -- the central entity of the quoting system.

A quote captures:
  - The customer and optional project it belongs to.
  - The price-book snapshot used for calculation (immutable after send).
  - The original QuoteParams and full CostBreakdown as JSONB blobs.
  - Three price tiers (low / standard / premium), the selected tier, and
    the engine-computed total cost and total price.
  - Confidence score, risk flags, review requirement.
  - Lifecycle timestamps (created, updated, locked, expires).
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuoteStatus(str, enum.Enum):
    """Lifecycle states for a quote."""

    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_customer_id", "customer_id"),
        Index("ix_quotes_status", "status"),
        Index("ix_quotes_created_at", "created_at"),
        Index("ix_quotes_quote_number", "quote_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quote_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )

    # -- Foreign keys --
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_book_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # -- Status --
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="quote_status", create_type=True),
        nullable=False,
        server_default=QuoteStatus.draft.value,
    )

    # -- Project classification --
    project_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # -- Calculation inputs / outputs (JSONB) --
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cost_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # -- Tier prices (Numeric, never Float) --
    tier_low_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    tier_standard_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    tier_premium_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    selected_tier: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    # -- Totals --
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # -- Risk / confidence --
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_flags: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    requires_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # -- Market context (added in migration 004) --
    market_snapshot_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    market_adjusted_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # -- Notes --
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Ownership --
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # -- Timestamps --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # -- Relationships --
    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="quotes", lazy="selectin"
    )
    project: Mapped["Project | None"] = relationship(
        "Project", back_populates="quotes", foreign_keys=[project_id], lazy="selectin"
    )
    snapshot: Mapped["PriceBookSnapshot"] = relationship(
        "PriceBookSnapshot", back_populates="quotes", lazy="selectin"
    )
    creator: Mapped["User"] = relationship(
        "User", back_populates="created_quotes",
        foreign_keys=[created_by], lazy="selectin",
    )
    negotiations: Mapped[list["NegotiationHistory"]] = relationship(
        "NegotiationHistory", back_populates="quote",
        cascade="all, delete-orphan", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Quote id={self.id} number={self.quote_number!r} "
            f"status={self.status.value} total_price={self.total_price}>"
        )
