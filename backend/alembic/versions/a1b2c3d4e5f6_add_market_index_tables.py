"""Add market index tables and extend snapshots/quotes

Revision ID: a1b2c3d4e5f6
Revises: cf15da76d787
Create Date: 2026-02-16 15:00:00.000000

New tables:
  - market_index_series    — What external indexes we track
  - market_index_observations — Each data point (effective-dated)
  - multiplier_rules       — How indexes become engine multipliers
  - multiplier_snapshots   — Frozen multipliers for quote reproducibility

Altered tables:
  - price_book_snapshots   — Add market_multipliers JSONB column
  - quotes                 — Add market_snapshot_date, market_adjusted_cost

All changes are additive. Rollback drops new columns/tables with zero data loss.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "cf15da76d787"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. market_index_series
    # ----------------------------------------------------------------
    op.create_table(
        "market_index_series",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("update_frequency", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("species", sa.String(length=100), nullable=True),
        sa.Column("grade", sa.String(length=50), nullable=True),
        sa.Column("geo", sa.String(length=100), server_default="US", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset", "category", "name", name="uq_series_dataset_category_name"),
    )
    op.create_index("ix_series_dataset_category", "market_index_series", ["dataset", "category"], unique=False)

    # ----------------------------------------------------------------
    # 2. market_index_observations
    # ----------------------------------------------------------------
    op.create_table(
        "market_index_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("value_numeric", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("geo", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("ingested_by", sa.String(length=100), server_default="manual", nullable=False),
        sa.CheckConstraint("value_numeric IS NOT NULL OR value_json IS NOT NULL", name="chk_observation_has_value"),
        sa.ForeignKeyConstraint(["series_id"], ["market_index_series.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "observed_date", name="uq_observation_series_date"),
    )
    op.create_index("ix_obs_series_date", "market_index_observations", ["series_id", "observed_date"], unique=False)
    op.create_index("ix_obs_ingested_at", "market_index_observations", ["ingested_at"], unique=False)

    # ----------------------------------------------------------------
    # 3. multiplier_rules
    # ----------------------------------------------------------------
    op.create_table(
        "multiplier_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("target_field", sa.String(length=100), nullable=False),
        sa.Column("formula", sa.String(length=20), server_default="ratio", nullable=False),
        sa.Column("baseline_value", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("baseline_date", sa.Date(), nullable=False),
        sa.Column("floor_mult", sa.Numeric(precision=8, scale=6), server_default="0.500000", nullable=False),
        sa.Column("ceiling_mult", sa.Numeric(precision=8, scale=6), server_default="3.000000", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("floor_mult <= ceiling_mult", name="chk_floor_lte_ceiling"),
        sa.CheckConstraint("floor_mult > 0", name="chk_floor_positive"),
        sa.CheckConstraint("baseline_value > 0", name="chk_baseline_positive"),
        sa.ForeignKeyConstraint(["series_id"], ["market_index_series.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "domain", "target_field", name="uq_rule_series_domain_target"),
    )

    # ----------------------------------------------------------------
    # 4. multiplier_snapshots
    # ----------------------------------------------------------------
    op.create_table(
        "multiplier_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("baseline_value", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("current_value", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["multiplier_rules.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "snapshot_date", name="uq_mult_snapshot_rule_date"),
    )
    op.create_index("ix_mult_snap_date", "multiplier_snapshots", ["snapshot_date"], unique=False)

    # ----------------------------------------------------------------
    # 5. Extend price_book_snapshots — add market_multipliers JSONB
    # ----------------------------------------------------------------
    op.add_column(
        "price_book_snapshots",
        sa.Column("market_multipliers", sa.JSON(), server_default="{}", nullable=True),
    )

    # ----------------------------------------------------------------
    # 6. Extend quotes — add market context columns
    # ----------------------------------------------------------------
    op.add_column(
        "quotes",
        sa.Column("market_snapshot_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "quotes",
        sa.Column("market_adjusted_cost", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    # Reverse order: drop columns first, then tables
    op.drop_column("quotes", "market_adjusted_cost")
    op.drop_column("quotes", "market_snapshot_date")
    op.drop_column("price_book_snapshots", "market_multipliers")

    op.drop_index("ix_mult_snap_date", table_name="multiplier_snapshots")
    op.drop_table("multiplier_snapshots")
    op.drop_table("multiplier_rules")
    op.drop_index("ix_obs_ingested_at", table_name="market_index_observations")
    op.drop_index("ix_obs_series_date", table_name="market_index_observations")
    op.drop_table("market_index_observations")
    op.drop_index("ix_series_dataset_category", table_name="market_index_series")
    op.drop_table("market_index_series")
