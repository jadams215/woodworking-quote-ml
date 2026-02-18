"""Market multipliers service — bridges DB market data to the pure engine.

This module reads market_index_observations and multiplier_rules from the
database, computes current multipliers, and builds a frozen MarketMultipliers
dataclass that can be passed into the pure quoting engine.

Side-effecting: performs database queries.  The returned MarketMultipliers
object is pure and frozen.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.engine.market_adjuster import MarketMultipliers
from app.models.market_index import (
    MarketIndexObservation,
    MarketIndexSeries,
    MultiplierRule,
    MultiplierSnapshot,
)
from app.utils.decimal_utils import to_decimal

_ONE = Decimal("1")
_ZERO = Decimal("0")


def get_latest_observation(
    db: Session, series_id: UUID
) -> MarketIndexObservation | None:
    """Get the most recent observation for a series."""
    return (
        db.query(MarketIndexObservation)
        .filter(MarketIndexObservation.series_id == series_id)
        .order_by(MarketIndexObservation.observed_date.desc())
        .first()
    )


def compute_multiplier(
    rule: MultiplierRule, current_value: Decimal
) -> Decimal:
    """Compute a clamped multiplier from a rule and current value.

    Formula types:
        - ratio:  current / baseline
        - delta:  1 + (current - baseline) / baseline  (same result as ratio)
        - step:   reserved for future discrete-tier logic

    The result is clamped to [floor_mult, ceiling_mult].
    """
    baseline = rule.baseline_value
    if baseline <= _ZERO:
        return _ONE

    if rule.formula in ("ratio", "delta"):
        mult = current_value / baseline
    else:
        mult = _ONE

    # Clamp
    if mult < rule.floor_mult:
        mult = rule.floor_mult
    if mult > rule.ceiling_mult:
        mult = rule.ceiling_mult

    return mult


def build_market_multipliers(
    db: Session, as_of: date | None = None
) -> MarketMultipliers:
    """Build a MarketMultipliers frozen dataclass from current DB state.

    Reads all active multiplier_rules, looks up the latest observation for
    each rule's series, computes the multiplier, and assembles the result.

    Returns ``MarketMultipliers.identity()`` if no rules are active.
    """
    if as_of is None:
        as_of = date.today()

    rules = (
        db.query(MultiplierRule)
        .filter(MultiplierRule.is_active.is_(True))
        .all()
    )

    if not rules:
        return MarketMultipliers.identity()

    material_multipliers: dict[str, Decimal] = {}
    labor_multiplier = _ONE
    fuel_surcharge_factor = _ONE
    demand_premium_factor = _ONE
    powder_coating_multiplier = _ONE
    subcontractor_multiplier = _ONE

    for rule in rules:
        obs = get_latest_observation(db, rule.series_id)
        if obs is None or obs.value_numeric is None:
            continue

        mult = compute_multiplier(rule, obs.value_numeric)

        if rule.domain == "material":
            material_multipliers[rule.target_field] = mult
        elif rule.domain == "labor":
            labor_multiplier = mult
        elif rule.domain == "fuel":
            fuel_surcharge_factor = mult
        elif rule.domain == "demand":
            demand_premium_factor = mult
        elif rule.domain == "finishing":
            powder_coating_multiplier = mult
        elif rule.domain == "subcontractor":
            subcontractor_multiplier = mult

    return MarketMultipliers(
        material_multipliers=material_multipliers,
        labor_multiplier=labor_multiplier,
        fuel_surcharge_factor=fuel_surcharge_factor,
        demand_premium_factor=demand_premium_factor,
        powder_coating_multiplier=powder_coating_multiplier,
        subcontractor_multiplier=subcontractor_multiplier,
        snapshot_date=as_of,
    )


def freeze_multipliers(
    db: Session, multipliers: MarketMultipliers
) -> list[MultiplierSnapshot]:
    """Freeze current multiplier values as snapshots for quote reproducibility.

    Creates MultiplierSnapshot rows for each active rule.  If a snapshot
    already exists for the rule+date combination, it is skipped (idempotent).

    Returns the list of created snapshot objects (not yet committed).
    """
    snap_date = multipliers.snapshot_date
    rules = (
        db.query(MultiplierRule)
        .filter(MultiplierRule.is_active.is_(True))
        .all()
    )

    created: list[MultiplierSnapshot] = []
    for rule in rules:
        # Check if snapshot already exists
        existing = (
            db.query(MultiplierSnapshot)
            .filter(
                MultiplierSnapshot.rule_id == rule.id,
                MultiplierSnapshot.snapshot_date == snap_date,
            )
            .first()
        )
        if existing:
            continue

        obs = get_latest_observation(db, rule.series_id)
        if obs is None or obs.value_numeric is None:
            continue

        mult = compute_multiplier(rule, obs.value_numeric)

        snapshot = MultiplierSnapshot(
            rule_id=rule.id,
            snapshot_date=snap_date,
            baseline_value=rule.baseline_value,
            current_value=obs.value_numeric,
            multiplier=mult,
        )
        db.add(snapshot)
        created.append(snapshot)

    db.flush()
    return created
