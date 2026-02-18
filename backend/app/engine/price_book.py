"""
Immutable PriceBook value object.

A PriceBook is a frozen snapshot of every cost table the engine needs.
It is created *outside* the engine (from database rows, from a JSON blob,
or from hard-coded defaults in tests) and passed *into* pure engine functions.

Purity guarantees
-----------------
- No ``sqlalchemy``, no ``os``, no ``pathlib``, no ``random``, no ``datetime.now()``.
- The only stdlib I/O-adjacent import is ``hashlib`` and ``json`` -- used
  exclusively for the deterministic SHA-256 hash of the canonical JSON form.
- All numeric values are ``Decimal``.  Zero ``float``.
- The dataclass is ``frozen=True``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict

from app.utils.decimal_utils import to_decimal


# ---------------------------------------------------------------------------
# PriceBook
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriceBook:
    """Immutable, Decimal-only container for all cost tables.

    Construction
    ------------
    Prefer the ``from_snapshot_data`` classmethod when hydrating from a
    JSON/JSONB blob.  The raw constructor is available for tests and for
    building a PriceBook from typed catalog rows in ``snapshot.py``.
    """

    # Material cost per board-foot keyed by species name
    material_costs_per_bf: Dict[str, Decimal]

    # Grade multipliers keyed by grade name (Economy / Standard / Premium)
    grade_multipliers: Dict[str, Decimal]

    # Waste factors keyed by grade name (as a decimal fraction, e.g. 0.10)
    waste_factors: Dict[str, Decimal]

    # Labor rates per hour keyed by department slug
    labor_rates: Dict[str, Decimal]

    # Finishing cost per sqft keyed by complexity level (int key as str)
    finishing_costs_per_sqft: Dict[str, Decimal]

    # Scalar rates
    overhead_pct: Decimal
    installation_multiplier: Decimal
    powder_coating_per_sqft: Decimal
    max_risk_adjustment_pct: Decimal

    # Complexity multipliers keyed by score (int key as str)
    complexity_multipliers: Dict[str, Decimal]

    # Delivery
    delivery_base_fee: Decimal
    delivery_per_mile: Decimal
    delivery_heavy_surcharge: Decimal

    # Margin targets keyed by tier name (low / standard / premium)
    margin_targets: Dict[str, Decimal]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_snapshot_data(cls, data: dict) -> PriceBook:
        """Parse a plain dict (e.g. from JSONB column) into a PriceBook.

        String values that represent numbers are converted to Decimal via
        ``to_decimal``.  Nested dicts have their values converted; top-level
        scalars are converted directly.
        """
        def _dec_dict(d: dict) -> Dict[str, Decimal]:
            return {str(k): to_decimal(v) for k, v in d.items()}

        delivery = data.get("delivery", {})

        return cls(
            material_costs_per_bf=_dec_dict(data.get("material_costs_per_bf", {})),
            grade_multipliers=_dec_dict(data.get("grade_multipliers", {})),
            waste_factors=_dec_dict(data.get("waste_factors", {})),
            labor_rates=_dec_dict(data.get("labor_rates", {})),
            finishing_costs_per_sqft=_dec_dict(data.get("finishing_costs_per_sqft", {})),
            overhead_pct=to_decimal(data.get("overhead_pct", "0.20")),
            installation_multiplier=to_decimal(data.get("installation_multiplier", "1.25")),
            powder_coating_per_sqft=to_decimal(data.get("powder_coating_per_sqft", "4.50")),
            max_risk_adjustment_pct=to_decimal(data.get("max_risk_adjustment_pct", "0.25")),
            complexity_multipliers=_dec_dict(data.get("complexity_multipliers", {})),
            delivery_base_fee=to_decimal(delivery.get("base_fee", "75.00")),
            delivery_per_mile=to_decimal(delivery.get("per_mile", "2.50")),
            delivery_heavy_surcharge=to_decimal(delivery.get("heavy_surcharge", "150.00")),
            margin_targets=_dec_dict(data.get("margin_targets", {
                "low": "25.00",
                "standard": "40.00",
                "premium": "55.00",
            })),
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (Decimals become strings).

        The structure mirrors what ``from_snapshot_data`` expects so that
        ``PriceBook.from_snapshot_data(pb.to_dict())`` is a lossless
        round-trip.
        """
        def _str_dict(d: Dict[str, Decimal]) -> Dict[str, str]:
            return {k: str(v) for k, v in d.items()}

        return {
            "material_costs_per_bf": _str_dict(self.material_costs_per_bf),
            "grade_multipliers": _str_dict(self.grade_multipliers),
            "waste_factors": _str_dict(self.waste_factors),
            "labor_rates": _str_dict(self.labor_rates),
            "finishing_costs_per_sqft": _str_dict(self.finishing_costs_per_sqft),
            "overhead_pct": str(self.overhead_pct),
            "installation_multiplier": str(self.installation_multiplier),
            "powder_coating_per_sqft": str(self.powder_coating_per_sqft),
            "max_risk_adjustment_pct": str(self.max_risk_adjustment_pct),
            "complexity_multipliers": _str_dict(self.complexity_multipliers),
            "delivery": {
                "base_fee": str(self.delivery_base_fee),
                "per_mile": str(self.delivery_per_mile),
                "heavy_surcharge": str(self.delivery_heavy_surcharge),
            },
            "margin_targets": _str_dict(self.margin_targets),
        }

    # ------------------------------------------------------------------
    # Deterministic hash
    # ------------------------------------------------------------------

    def to_sha256(self) -> str:
        """Compute a deterministic SHA-256 hex digest.

        The canonical form is compact JSON with sorted keys and no trailing
        whitespace.  Because all numeric values are serialized as strings
        (via ``to_dict``), the representation is platform-independent and
        does not depend on float formatting.
        """
        canonical = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Convenience look-ups (with safe defaults)
    # ------------------------------------------------------------------

    def species_cost(self, species: str) -> Decimal:
        """Look up material cost per BF, falling back to 'Other'."""
        return self.material_costs_per_bf.get(
            species,
            self.material_costs_per_bf.get("Other", Decimal("6.00")),
        )

    def grade_multiplier(self, grade: str) -> Decimal:
        """Look up grade multiplier, falling back to Standard."""
        return self.grade_multipliers.get(
            grade,
            self.grade_multipliers.get("Standard", Decimal("1.00")),
        )

    def waste_factor(self, grade: str) -> Decimal:
        """Look up waste factor for a grade, falling back to Standard."""
        return self.waste_factors.get(
            grade,
            self.waste_factors.get("Standard", Decimal("0.10")),
        )

    def finishing_rate(self, complexity: int) -> Decimal:
        """Look up finishing rate per sqft by complexity level (1-5)."""
        return self.finishing_costs_per_sqft.get(
            str(complexity),
            self.finishing_costs_per_sqft.get("3", Decimal("5.00")),
        )

    def complexity_multiplier(self, score: int) -> Decimal:
        """Look up complexity multiplier by score (1-5)."""
        return self.complexity_multipliers.get(
            str(score),
            self.complexity_multipliers.get("3", Decimal("1.00")),
        )

    def labor_rate(self, department: str) -> Decimal:
        """Look up hourly labor rate by department slug."""
        return self.labor_rates.get(
            department,
            self.labor_rates.get("general", Decimal("45.00")),
        )

    def margin_target(self, tier: str) -> Decimal:
        """Look up margin target percentage by tier name."""
        return self.margin_targets.get(
            tier,
            Decimal("40.00"),
        )
