"""Tracking models -- post-quote lifecycle records.

LostQuote:           Captures competitive-loss data for pricing feedback loops.
CompletedProject:    Actual cost vs. quoted cost for margin analysis.
NegotiationHistory:  Price adjustment trail attached to a quote (CASCADE on delete).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LostQuote(Base):
    __tablename__ = "lost_quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("quotes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    winning_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    competitor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    quote = relationship("Quote")
    recorder = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<LostQuote id={self.id} quote_id={self.quote_id} "
            f"original={self.original_price} winning={self.winning_price}>"
        )


class CompletedProject(Base):
    __tablename__ = "completed_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("quotes.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # -- Original quote figures --
    quoted_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quoted_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    final_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # -- Actual costs --
    actual_material_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    actual_labor_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    actual_overhead_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    actual_total_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )

    # -- Margin --
    margin_achieved_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )

    # -- Qualitative feedback --
    customer_satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Timestamps / ownership --
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    recorded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    project = relationship("Project", back_populates="completed_records")
    quote = relationship("Quote")
    recorder = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<CompletedProject id={self.id} project_id={self.project_id} "
            f"margin={self.margin_achieved_pct}%>"
        )


class NegotiationHistory(Base):
    __tablename__ = "negotiation_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    adjustment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    quote = relationship("Quote", back_populates="negotiations")
    creator = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<NegotiationHistory id={self.id} quote_id={self.quote_id} "
            f"old={self.old_price} new={self.new_price}>"
        )
