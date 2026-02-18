"""
Pure cost-calculation functions for the woodworking quoting engine.

Every function in this module is a **pure function**: given the same inputs it
always returns the same outputs, and it performs zero side effects (no I/O, no
database, no network, no file system, no randomness, no clock reads).

All monetary and dimensional arithmetic uses ``decimal.Decimal``.  There is
not a single ``float`` in this module.

Rounding policy
---------------
- Intermediate calculations preserve full Decimal precision.
- ``round_money`` (2 decimal places, ROUND_HALF_UP) is applied only when
  producing a final monetary output that will be stored or displayed.
- The orchestrator in ``quote_generator.py`` calls ``round_money`` on the
  final ``CostBreakdown`` fields; individual helpers here return
  *unrounded* Decimals so that the caller can decide when to round.

Imports allowed
---------------
Only ``decimal``, ``typing``, and sibling engine modules.
``app.utils.decimal_utils`` is permitted (pure helpers, no I/O).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from app.engine.market_adjuster import (
    MarketMultipliers,
    apply_fuel_surcharge,
    apply_labor_market_adjustment,
    apply_material_market_adjustment,
    apply_powder_coating_adjustment,
)
from app.engine.price_book import PriceBook
from app.engine.types import CostBreakdown, QuoteParams
from app.utils.decimal_utils import round_money, to_decimal


# ---------------------------------------------------------------------------
# Constants -- expressed as Decimal string literals
# ---------------------------------------------------------------------------
_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_HUNDRED = Decimal("100")
_BF_DIVISOR = Decimal("144")  # 12 in x 12 in = 144 sq-in per board-foot
_HEAVY_VOLUME_THRESHOLD = Decimal("50000")  # cubic-inch proxy for heavy item
_DEFAULT_INSTALL_FRACTION = Decimal("0.25")  # fraction of labor hours for install estimate


# ---------------------------------------------------------------------------
# Board-foot and surface-area geometry
# ---------------------------------------------------------------------------

def calculate_board_feet(
    length_in: Decimal,
    width_in: Decimal,
    height_in: Decimal,
) -> Decimal:
    """Compute board-feet from dimensions in inches.

    Formula: (length * width * height) / 144

    Preconditions
    -------------
    - All dimensions >= 0.
    - Passing negative values raises ``ValueError``.

    Returns full-precision Decimal (not rounded).
    """
    for name, val in (("length_in", length_in), ("width_in", width_in), ("height_in", height_in)):
        if val < _ZERO:
            raise ValueError(f"{name} must be non-negative, got {val}")
    return (length_in * width_in * height_in) / _BF_DIVISOR


def calculate_surface_area_sqft(
    length_in: Decimal,
    width_in: Decimal,
    height_in: Decimal,
) -> Decimal:
    """Compute surface area of a rectangular solid in square feet.

    Formula: 2 * ((L*W) + (W*H) + (H*L)) / 144

    Preconditions: all dimensions >= 0.
    """
    for name, val in (("length_in", length_in), ("width_in", width_in), ("height_in", height_in)):
        if val < _ZERO:
            raise ValueError(f"{name} must be non-negative, got {val}")
    return _TWO * (
        (length_in * width_in)
        + (width_in * height_in)
        + (height_in * length_in)
    ) / _BF_DIVISOR


# ---------------------------------------------------------------------------
# Material cost
# ---------------------------------------------------------------------------

def calculate_material_cost(
    board_feet: Decimal,
    species: str,
    grade: str,
    quantity: int,
    price_book: PriceBook,
) -> Decimal:
    """Compute raw-material cost including waste.

    Formula
    -------
    base = board_feet * species_cost * grade_multiplier * quantity
    waste = base * waste_factor
    total = base + waste   (equivalently, base * (1 + waste_factor))

    Preconditions
    -------------
    - ``board_feet >= 0``
    - ``quantity >= 0``
    - ``species`` and ``grade`` should be valid keys in the price book;
      unknown values fall back to safe defaults (see PriceBook look-ups).
    """
    if board_feet < _ZERO:
        raise ValueError(f"board_feet must be non-negative, got {board_feet}")
    if quantity < 0:
        raise ValueError(f"quantity must be non-negative, got {quantity}")

    species_cost = price_book.species_cost(species)
    grade_mult = price_book.grade_multiplier(grade)
    waste = price_book.waste_factor(grade)

    base = board_feet * species_cost * grade_mult * Decimal(str(quantity))
    return base * (_ONE + waste)


# ---------------------------------------------------------------------------
# Labor cost
# ---------------------------------------------------------------------------

def calculate_labor_cost(
    estimated_hours: Decimal,
    machine_hours: Decimal,
    has_woodwork: bool,
    has_metalwork: bool,
    has_finishing: bool,
    has_upholstery: bool,
    installation_hours: Decimal,
    price_book: PriceBook,
) -> Dict[str, Decimal]:
    """Compute labor cost split by department.

    Labour hours are divided evenly across the *active* departments
    (woodwork, metalwork, finishing, upholstery).  If none are flagged,
    woodwork is assumed.  Machine hours and installation hours are
    accounted separately.

    Returns
    -------
    Dict with keys like ``"woodwork"``, ``"metalwork"``, ``"finishing"``,
    ``"upholstery"``, ``"machine"``, ``"installation"`` mapped to their
    cost Decimals.  Missing departments have value ``Decimal("0")``.
    """
    if estimated_hours < _ZERO:
        raise ValueError(f"estimated_hours must be non-negative, got {estimated_hours}")
    if machine_hours < _ZERO:
        raise ValueError(f"machine_hours must be non-negative, got {machine_hours}")
    if installation_hours < _ZERO:
        raise ValueError(f"installation_hours must be non-negative, got {installation_hours}")

    active_depts: List[str] = []
    if has_woodwork:
        active_depts.append("woodwork")
    if has_metalwork:
        active_depts.append("metalwork")
    if has_finishing:
        active_depts.append("finishing")
    if has_upholstery:
        active_depts.append("upholstery")

    if not active_depts:
        active_depts = ["woodwork"]

    hours_per_dept = estimated_hours / Decimal(str(len(active_depts)))

    result: Dict[str, Decimal] = {
        "woodwork": _ZERO,
        "metalwork": _ZERO,
        "finishing": _ZERO,
        "upholstery": _ZERO,
        "machine": _ZERO,
        "installation": _ZERO,
    }

    for dept in active_depts:
        result[dept] = hours_per_dept * price_book.labor_rate(dept)

    # Machine hours
    result["machine"] = machine_hours * price_book.labor_rate("machine")

    # Installation (rate * multiplier)
    if installation_hours > _ZERO:
        result["installation"] = (
            installation_hours
            * price_book.labor_rate("installation")
            * price_book.installation_multiplier
        )

    return result


# ---------------------------------------------------------------------------
# Finishing cost
# ---------------------------------------------------------------------------

def calculate_finishing_cost(
    surface_area_sqft: Decimal,
    complexity: int,
    has_powder_coating: bool,
    price_book: PriceBook,
) -> Tuple[Decimal, Decimal]:
    """Compute finishing material cost and powder-coating cost.

    Parameters
    ----------
    surface_area_sqft : total surface area (already multiplied by quantity
                        if appropriate).
    complexity : finishing complexity level 1-5.
    has_powder_coating : whether powder coating is required.

    Returns
    -------
    ``(finish_material_cost, powder_coating_cost)`` -- both unrounded.
    """
    if surface_area_sqft < _ZERO:
        raise ValueError(f"surface_area_sqft must be non-negative, got {surface_area_sqft}")
    if not (1 <= complexity <= 5):
        raise ValueError(f"finishing complexity must be 1-5, got {complexity}")

    finish_cost = surface_area_sqft * price_book.finishing_rate(complexity)

    powder_cost = _ZERO
    if has_powder_coating:
        powder_cost = surface_area_sqft * price_book.powder_coating_per_sqft

    return finish_cost, powder_cost


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def calculate_delivery_cost(
    miles: Decimal,
    is_heavy: bool,
    price_book: PriceBook,
) -> Decimal:
    """Compute delivery cost.

    Formula: base_fee + (miles * per_mile) + heavy_surcharge_if_applicable
    Returns Decimal("0") when ``miles <= 0``.
    """
    if miles < _ZERO:
        raise ValueError(f"miles must be non-negative, got {miles}")
    if miles == _ZERO:
        return _ZERO

    cost = price_book.delivery_base_fee + (miles * price_book.delivery_per_mile)
    if is_heavy:
        cost += price_book.delivery_heavy_surcharge
    return cost


# ---------------------------------------------------------------------------
# Overhead
# ---------------------------------------------------------------------------

def calculate_overhead(
    direct_costs: Decimal,
    price_book: PriceBook,
) -> Decimal:
    """Compute overhead as a percentage of direct costs."""
    if direct_costs < _ZERO:
        raise ValueError(f"direct_costs must be non-negative, got {direct_costs}")
    return direct_costs * price_book.overhead_pct


# ---------------------------------------------------------------------------
# Complexity adjustment
# ---------------------------------------------------------------------------

def apply_complexity_adjustment(
    base: Decimal,
    score: int,
    price_book: PriceBook,
) -> Decimal:
    """Compute the complexity adjustment amount.

    Returns ``base * (multiplier - 1)`` so the result is the *delta* only
    (positive for complex jobs, negative for simple ones, zero for standard).
    """
    if base < _ZERO:
        raise ValueError(f"base must be non-negative, got {base}")
    multiplier = price_book.complexity_multiplier(score)
    return base * (multiplier - _ONE)


# ---------------------------------------------------------------------------
# Risk adjustment
# ---------------------------------------------------------------------------

def apply_risk_adjustment(
    base: Decimal,
    risk_pct: Decimal,
    price_book: PriceBook,
) -> Decimal:
    """Compute the risk adjustment amount.

    ``risk_pct`` is the user-supplied percentage (e.g. ``Decimal("5")``
    means 5%).  The actual rate is capped at ``max_risk_adjustment_pct``
    from the price book (which is stored as a fraction, e.g. ``0.25``).

    Formula: ``base * min(risk_pct / 100, max_risk_cap)``
    """
    if base < _ZERO:
        raise ValueError(f"base must be non-negative, got {base}")
    actual_rate = min(risk_pct / _HUNDRED, price_book.max_risk_adjustment_pct)
    # If risk_pct is negative, clamp to zero -- never reduce cost via risk
    if actual_rate < _ZERO:
        actual_rate = _ZERO
    return base * actual_rate


# ---------------------------------------------------------------------------
# Full cost breakdown (orchestrator)
# ---------------------------------------------------------------------------

def calculate_total_cost(
    params: QuoteParams,
    price_book: PriceBook,
    market: MarketMultipliers | None = None,
) -> CostBreakdown:
    """Compute a complete CostBreakdown from QuoteParams and a PriceBook.

    This is a pure function.  No I/O.  No side effects.

    Parameters
    ----------
    params : QuoteParams — the job's input parameters.
    price_book : PriceBook — base cost tables (your company's rates).
    market : MarketMultipliers | None — optional market index multipliers.
        When provided, base costs are adjusted by live market signals
        (lumber indexes, labor benchmarks, fuel prices, demand).
        When ``None``, no market adjustments are applied (backward compatible).

    Rounding: ``round_money`` is applied to every monetary field in the
    returned CostBreakdown so that downstream consumers see cent-precise
    values.  Intermediate sums are computed from the *unrounded*
    constituent parts to avoid double-rounding drift; the rounded total
    fields are the authoritative values.
    """
    # -- geometry ----------------------------------------------------------
    board_feet = calculate_board_feet(
        params.length_in, params.width_in, params.height_in,
    )
    surface_area_sqft = calculate_surface_area_sqft(
        params.length_in, params.width_in, params.height_in,
    )
    total_surface_area = surface_area_sqft * Decimal(str(params.quantity))

    # -- materials ---------------------------------------------------------
    material_cost = calculate_material_cost(
        board_feet, params.wood_species, params.material_grade,
        params.quantity, price_book,
    )
    # Apply market adjustment to material cost
    material_cost = apply_material_market_adjustment(
        material_cost, params.wood_species, params.material_grade, market,
    )

    hardware_cost = params.hardware_cost

    finish_material_cost, powder_coating_cost = calculate_finishing_cost(
        total_surface_area,
        params.finishing_complexity,
        params.has_powder_coating,
        price_book,
    )
    # Apply market adjustment to powder coating
    powder_coating_cost = apply_powder_coating_adjustment(powder_coating_cost, market)

    total_material_cost = (
        material_cost + hardware_cost + finish_material_cost + powder_coating_cost
    )

    # -- labor -------------------------------------------------------------
    # Estimate installation hours if required but not explicitly provided
    installation_hours: Decimal
    if params.installation_required:
        installation_hours = params.estimated_labor_hours * _DEFAULT_INSTALL_FRACTION
    else:
        installation_hours = _ZERO

    labor = calculate_labor_cost(
        estimated_hours=params.estimated_labor_hours,
        machine_hours=params.estimated_machine_hours,
        has_woodwork=params.has_woodwork,
        has_metalwork=params.has_metalwork,
        has_finishing=params.has_finishing,
        has_upholstery=params.has_upholstery,
        installation_hours=installation_hours,
        price_book=price_book,
    )
    # Apply market adjustment to each labor department cost
    labor = {
        dept: apply_labor_market_adjustment(cost, market)
        for dept, cost in labor.items()
    }

    total_labor_cost = sum(labor.values(), _ZERO)

    # -- delivery ----------------------------------------------------------
    volume = (
        params.length_in * params.width_in * params.height_in
        * Decimal(str(params.quantity))
    )
    is_heavy = volume > _HEAVY_VOLUME_THRESHOLD

    delivery_cost: Decimal
    if params.delivery_miles > _ZERO:
        delivery_cost = calculate_delivery_cost(
            params.delivery_miles, is_heavy, price_book,
        )
        # Apply fuel surcharge to delivery cost
        delivery_cost = apply_fuel_surcharge(delivery_cost, market)
    else:
        delivery_cost = _ZERO

    # -- direct cost total -------------------------------------------------
    total_direct_cost = total_material_cost + total_labor_cost + delivery_cost

    # -- overhead ----------------------------------------------------------
    overhead_cost = calculate_overhead(total_direct_cost, price_book)

    # -- adjustments -------------------------------------------------------
    base_for_adjustments = total_direct_cost + overhead_cost

    complexity_adjustment = apply_complexity_adjustment(
        base_for_adjustments, params.job_complexity_score, price_book,
    )
    risk_adjustment = apply_risk_adjustment(
        base_for_adjustments, params.risk_adjustment_pct, price_book,
    )

    # -- total cost --------------------------------------------------------
    total_cost = (
        total_direct_cost
        + overhead_cost
        + complexity_adjustment
        + risk_adjustment
    )

    # -- build frozen result (round each monetary field) -------------------
    return CostBreakdown(
        material_cost=round_money(material_cost),
        hardware_cost=round_money(hardware_cost),
        finish_material_cost=round_money(finish_material_cost),
        powder_coating_cost=round_money(powder_coating_cost),
        total_material_cost=round_money(total_material_cost),
        labor_cost_woodwork=round_money(labor.get("woodwork", _ZERO)),
        labor_cost_metalwork=round_money(labor.get("metalwork", _ZERO)),
        labor_cost_finishing=round_money(labor.get("finishing", _ZERO)),
        labor_cost_upholstery=round_money(labor.get("upholstery", _ZERO)),
        labor_cost_machine=round_money(labor.get("machine", _ZERO)),
        labor_cost_installation=round_money(labor.get("installation", _ZERO)),
        total_labor_cost=round_money(total_labor_cost),
        delivery_cost=round_money(delivery_cost),
        overhead_cost=round_money(overhead_cost),
        complexity_adjustment=round_money(complexity_adjustment),
        risk_adjustment=round_money(risk_adjustment),
        total_direct_cost=round_money(total_direct_cost),
        total_cost=round_money(total_cost),
    )
