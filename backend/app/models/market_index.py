"""Market index models — external pricing signals for market-adjusted quoting.

Four tables:

1. ``market_index_series``   — *What* we track (e.g. "Walnut FAS 4/4 Appalachian").
2. ``market_index_observations`` — Each data point for a series (effective-dated).
3. ``multiplier_rules``      — *How* an index becomes an engine multiplier
                                (formula, baseline, floor/ceiling).
4. ``multiplier_snapshots``  — Frozen multiplier values at quote-send time
                                for reproducibility.

Money columns use NUMERIC, never FLOAT.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# market_index_series — What we track
# ---------------------------------------------------------------------------

class MarketIndexSeries(Base):
    """A named external data series that we periodically ingest.

    Examples:
        - "Walnut FAS 4/4 Appalachian" (HMR wholesale lumber)
        - "BLS Cabinetmaker Median Hourly Wage, Atlanta"
        - "EIA U.S. No 2 Diesel Retail"
        - "Dodge Momentum Index (nonresidential)"
    """

    __tablename__ = "market_index_series"
    __table_args__ = (
        UniqueConstraint(
            "dataset", "category", "name",
            name="uq_series_dataset_category_name",
        ),
        Index("ix_series_dataset_category", "dataset", "category"),
        Index(
            "ix_series_species_grade",
            "species", "grade",
            postgresql_where="species IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="monthly"
    )
    species: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    geo: Mapped[str] = mapped_column(String(100), nullable=False, server_default="US")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # -- Relationships --
    observations: Mapped[list["MarketIndexObservation"]] = relationship(
        "MarketIndexObservation", back_populates="series",
        cascade="all, delete-orphan", lazy="selectin",
    )
    multiplier_rules: Mapped[list["MultiplierRule"]] = relationship(
        "MultiplierRule", back_populates="series", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<MarketIndexSeries id={self.id} dataset={self.dataset!r} "
            f"name={self.name!r}>"
        )


# ---------------------------------------------------------------------------
# market_index_observations — Each data point
# ---------------------------------------------------------------------------

class MarketIndexObservation(Base):
    """A single observation (price, rate, index value) for a series on a date.

    Either ``value_numeric`` or ``value_json`` must be non-NULL.
    Use ``value_numeric`` for scalar data (lumber $/bf, diesel $/gal).
    Use ``value_json`` for structured data (BLS percentiles, tier pricing).
    """

    __tablename__ = "market_index_observations"
    __table_args__ = (
        UniqueConstraint(
            "series_id", "observed_date",
            name="uq_observation_series_date",
        ),
        CheckConstraint(
            "value_numeric IS NOT NULL OR value_json IS NOT NULL",
            name="chk_observation_has_value",
        ),
        Index("ix_obs_series_date", "series_id", "observed_date"),
        Index("ix_obs_ingested_at", "ingested_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_index_series.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6), nullable=True
    )
    value_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    geo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ingested_by: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="manual"
    )

    # -- Relationships --
    series: Mapped["MarketIndexSeries"] = relationship(
        "MarketIndexSeries", back_populates="observations", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<MarketIndexObservation id={self.id} "
            f"series_id={self.series_id} date={self.observed_date} "
            f"value={self.value_numeric}>"
        )


# ---------------------------------------------------------------------------
# multiplier_rules — How indexes become adjustments
# ---------------------------------------------------------------------------

class MultiplierRule(Base):
    """Defines how a market index series translates to an engine multiplier.

    Formula types:
        - ``ratio``:  multiplier = current / baseline
        - ``delta``:  multiplier = 1 + (current - baseline) / baseline
        - ``step``:   predefined thresholds (for demand signals)

    The ``floor_mult`` and ``ceiling_mult`` clamp the computed multiplier to
    prevent extreme adjustments from bad data or market dislocations.
    """

    __tablename__ = "multiplier_rules"
    __table_args__ = (
        UniqueConstraint(
            "series_id", "domain", "target_field",
            name="uq_rule_series_domain_target",
        ),
        CheckConstraint(
            "floor_mult <= ceiling_mult",
            name="chk_floor_lte_ceiling",
        ),
        CheckConstraint(
            "floor_mult > 0",
            name="chk_floor_positive",
        ),
        CheckConstraint(
            "baseline_value > 0",
            name="chk_baseline_positive",
        ),
        Index(
            "ix_rule_domain_active",
            "domain",
            postgresql_where="is_active = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_index_series.id", ondelete="RESTRICT"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False)
    formula: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ratio"
    )
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    baseline_date: Mapped[date] = mapped_column(Date, nullable=False)
    floor_mult: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, server_default="0.500000"
    )
    ceiling_mult: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, server_default="3.000000"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # -- Relationships --
    series: Mapped["MarketIndexSeries"] = relationship(
        "MarketIndexSeries", back_populates="multiplier_rules", lazy="selectin",
    )
    snapshots: Mapped[list["MultiplierSnapshot"]] = relationship(
        "MultiplierSnapshot", back_populates="rule",
        cascade="all, delete-orphan", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<MultiplierRule id={self.id} domain={self.domain!r} "
            f"target={self.target_field!r} baseline={self.baseline_value}>"
        )


# ---------------------------------------------------------------------------
# multiplier_snapshots — Frozen for quote reproducibility
# ---------------------------------------------------------------------------

class MultiplierSnapshot(Base):
    """A frozen multiplier value at a point in time.

    When a quote is sent, we freeze each active multiplier's computed value
    so that the quote can be reproduced months later.

    Write-once: these rows must never be updated or deleted.
    """

    __tablename__ = "multiplier_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "snapshot_date",
            name="uq_mult_snapshot_rule_date",
        ),
        Index("ix_mult_snap_date", "snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("multiplier_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # -- Relationships --
    rule: Mapped["MultiplierRule"] = relationship(
        "MultiplierRule", back_populates="snapshots", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<MultiplierSnapshot id={self.id} rule_id={self.rule_id} "
            f"date={self.snapshot_date} mult={self.multiplier}>"
        )
