"""
Frozen value objects for the quoting engine.

Every type here is an immutable dataclass with Decimal-only numeric fields.
These objects cross the boundary between the pure engine and the outside world
(API layer, persistence layer) but contain zero I/O logic themselves.

Purity guarantees
-----------------
- No imports of ``os``, ``random``, ``sqlalchemy``, ``pathlib``, or any I/O lib.
- All numeric fields are ``Decimal``.  There is no ``float`` anywhere.
- All dataclasses are ``frozen=True`` so instances cannot be mutated after
  creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuoteParams:
    """Immutable input parameters for a single quote calculation.

    Every numeric field is Decimal.  The caller (API layer) is responsible for
    converting user input to Decimal before constructing this object.
    """

    # -- Dimensions (inches) -------------------------------------------------
    length_in: Decimal
    width_in: Decimal
    height_in: Decimal
    quantity: int

    # -- Materials -----------------------------------------------------------
    wood_species: str
    material_grade: str  # Economy / Standard / Premium

    # -- Project classification ----------------------------------------------
    project_type: str  # conference_table, credenza, built_in, coffee_table, custom

    # -- Labor ---------------------------------------------------------------
    estimated_labor_hours: Decimal
    estimated_machine_hours: Decimal

    # -- Work-type flags -----------------------------------------------------
    has_woodwork: bool
    has_metalwork: bool
    has_finishing: bool
    has_upholstery: bool
    has_powder_coating: bool

    # -- Finishing -----------------------------------------------------------
    finishing_complexity: int  # 1-5

    # -- Hardware ------------------------------------------------------------
    hardware_cost: Decimal

    # -- Logistics -----------------------------------------------------------
    delivery_miles: Decimal
    installation_required: bool

    # -- Risk / complexity ---------------------------------------------------
    job_complexity_score: int  # 1-5
    risk_adjustment_pct: Decimal  # e.g. Decimal("5") means 5 %


# ---------------------------------------------------------------------------
# Output -- cost breakdown
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CostBreakdown:
    """Immutable detailed cost breakdown.  All monetary fields are Decimal."""

    # -- Materials -----------------------------------------------------------
    material_cost: Decimal
    hardware_cost: Decimal
    finish_material_cost: Decimal
    powder_coating_cost: Decimal
    total_material_cost: Decimal

    # -- Labor (by department) -----------------------------------------------
    labor_cost_woodwork: Decimal
    labor_cost_metalwork: Decimal
    labor_cost_finishing: Decimal
    labor_cost_upholstery: Decimal
    labor_cost_machine: Decimal
    labor_cost_installation: Decimal
    total_labor_cost: Decimal

    # -- Indirect / logistics ------------------------------------------------
    delivery_cost: Decimal
    overhead_cost: Decimal

    # -- Adjustments ---------------------------------------------------------
    complexity_adjustment: Decimal
    risk_adjustment: Decimal

    # -- Totals --------------------------------------------------------------
    total_direct_cost: Decimal
    total_cost: Decimal


# ---------------------------------------------------------------------------
# Output -- pricing tier
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuoteTier:
    """A single pricing tier (e.g. low / standard / premium)."""

    name: str
    price: Decimal
    margin_pct: Decimal


# ---------------------------------------------------------------------------
# Output -- complete quote result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuoteResult:
    """Complete, immutable result of a quote generation run.

    The ``quote_id`` and ``generated_at`` fields are *injected* by the caller
    -- the engine never generates IDs or reads the clock.
    """

    cost_breakdown: CostBreakdown

    # Pricing tiers
    tier_low: QuoteTier
    tier_standard: QuoteTier
    tier_premium: QuoteTier

    # Confidence
    confidence_score: int   # 0-100
    confidence_level: str   # Low / Medium / High

    # Risk
    risk_flags: Tuple[str, ...]  # immutable sequence
    requires_review: bool

    # Reproducibility
    snapshot_hash: str  # SHA-256 hex digest of the PriceBook used

    # Identity (injected, not generated)
    quote_id: str
    generated_at: datetime
