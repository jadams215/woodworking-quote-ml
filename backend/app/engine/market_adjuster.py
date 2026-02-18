"""
Pure market-adjustment functions for the quoting engine.

MarketMultipliers is a frozen dataclass that captures market index data
(lumber prices, labor benchmarks, fuel costs, demand signals) and translates
them into multipliers that adjust the base PriceBook rates.

Purity guarantees
-----------------
- No ``sqlalchemy``, no ``os``, no ``pathlib``, no ``random``, no ``datetime.now()``.
- The only stdlib I/O-adjacent import is ``hashlib`` and ``json`` — used
  exclusively for the deterministic SHA-256 hash.
- All numeric values are ``Decimal``.  Zero ``float``.
- The dataclass is ``frozen=True``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict

from app.utils.decimal_utils import to_decimal


_ONE = Decimal("1")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class MarketMultipliers:
    """Immutable market-index multipliers for adjusting PriceBook base rates.

    Each multiplier is a ratio: ``current_market_value / baseline_value``.
    A multiplier of ``1.0`` means no adjustment.  ``1.15`` means a 15% increase.

    Multipliers are clamped to ``[floor, ceiling]`` at computation time by
    the service layer — the engine trusts the values it receives.

    Construction
    ------------
    Prefer ``from_snapshot_data`` when hydrating from a JSONB blob.
    The raw constructor is available for tests.
    """

    # Material multipliers keyed by "species:grade" (e.g. "Walnut:FAS")
    # Missing keys mean no adjustment (multiplier = 1.0)
    material_multipliers: Dict[str, Decimal] = field(default_factory=dict)

    # Single labor multiplier applied to all department rates
    labor_multiplier: Decimal = _ONE

    # Fuel surcharge factor applied to delivery per-mile rate
    fuel_surcharge_factor: Decimal = _ONE

    # Demand premium applied to margin targets
    demand_premium_factor: Decimal = _ONE

    # Powder coating multiplier
    powder_coating_multiplier: Decimal = _ONE

    # Subcontractor rate multiplier (CNC, etc.)
    subcontractor_multiplier: Decimal = _ONE

    # When these multipliers were computed
    snapshot_date: date = field(default_factory=date.today)

    # ------------------------------------------------------------------
    # Look-ups
    # ------------------------------------------------------------------

    def material_multiplier(self, species: str, grade: str) -> Decimal:
        """Look up material multiplier for a species:grade pair.

        Falls back to species-only key, then to ``1.0`` (no adjustment).
        """
        key = f"{species}:{grade}"
        mult = self.material_multipliers.get(key)
        if mult is not None:
            return mult
        # Try species-only fallback
        for k, v in self.material_multipliers.items():
            if k.startswith(f"{species}:"):
                return v
        return _ONE

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (Decimals become strings)."""
        return {
            "material_multipliers": {k: str(v) for k, v in self.material_multipliers.items()},
            "labor_multiplier": str(self.labor_multiplier),
            "fuel_surcharge_factor": str(self.fuel_surcharge_factor),
            "demand_premium_factor": str(self.demand_premium_factor),
            "powder_coating_multiplier": str(self.powder_coating_multiplier),
            "subcontractor_multiplier": str(self.subcontractor_multiplier),
            "snapshot_date": self.snapshot_date.isoformat(),
        }

    @classmethod
    def from_snapshot_data(cls, data: dict) -> MarketMultipliers:
        """Parse a plain dict (e.g. from JSONB column) into MarketMultipliers."""
        mat_mults = {
            str(k): to_decimal(v) for k, v in data.get("material_multipliers", {}).items()
        }

        snapshot_date_str = data.get("snapshot_date")
        if snapshot_date_str and isinstance(snapshot_date_str, str):
            snap_date = date.fromisoformat(snapshot_date_str)
        elif isinstance(snapshot_date_str, date):
            snap_date = snapshot_date_str
        else:
            snap_date = date.today()

        return cls(
            material_multipliers=mat_mults,
            labor_multiplier=to_decimal(data.get("labor_multiplier", "1")),
            fuel_surcharge_factor=to_decimal(data.get("fuel_surcharge_factor", "1")),
            demand_premium_factor=to_decimal(data.get("demand_premium_factor", "1")),
            powder_coating_multiplier=to_decimal(data.get("powder_coating_multiplier", "1")),
            subcontractor_multiplier=to_decimal(data.get("subcontractor_multiplier", "1")),
            snapshot_date=snap_date,
        )

    # ------------------------------------------------------------------
    # Deterministic hash
    # ------------------------------------------------------------------

    def to_sha256(self) -> str:
        """Compute a deterministic SHA-256 hex digest."""
        canonical = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Identity (no market adjustments)
    # ------------------------------------------------------------------

    @classmethod
    def identity(cls) -> MarketMultipliers:
        """Return a multiplier set that applies no adjustments (all 1.0)."""
        return cls()


# ---------------------------------------------------------------------------
# Pure adjustment functions
# ---------------------------------------------------------------------------

def apply_material_market_adjustment(
    base_cost: Decimal,
    species: str,
    grade: str,
    market: MarketMultipliers | None,
) -> Decimal:
    """Adjust a material cost by the market multiplier.

    Returns ``base_cost`` unchanged if ``market`` is None or no multiplier
    exists for the given species/grade.
    """
    if market is None:
        return base_cost
    mult = market.material_multiplier(species, grade)
    return base_cost * mult


def apply_labor_market_adjustment(
    base_cost: Decimal,
    market: MarketMultipliers | None,
) -> Decimal:
    """Adjust a labor cost by the market labor multiplier."""
    if market is None:
        return base_cost
    return base_cost * market.labor_multiplier


def apply_fuel_surcharge(
    base_delivery_cost: Decimal,
    market: MarketMultipliers | None,
) -> Decimal:
    """Adjust delivery cost by the fuel surcharge factor."""
    if market is None:
        return base_delivery_cost
    return base_delivery_cost * market.fuel_surcharge_factor


def apply_powder_coating_adjustment(
    base_cost: Decimal,
    market: MarketMultipliers | None,
) -> Decimal:
    """Adjust powder coating cost by market multiplier."""
    if market is None:
        return base_cost
    return base_cost * market.powder_coating_multiplier


def apply_demand_premium(
    margin_pct: Decimal,
    market: MarketMultipliers | None,
) -> Decimal:
    """Adjust margin percentage by the demand premium factor.

    When demand is high (factor > 1.0), margins increase.
    When demand is low (factor < 1.0), margins compress.
    The adjustment is additive: margin + (margin * (factor - 1)).
    """
    if market is None:
        return margin_pct
    adjustment = margin_pct * (market.demand_premium_factor - _ONE)
    return margin_pct + adjustment
