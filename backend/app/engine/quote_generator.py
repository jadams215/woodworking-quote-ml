"""
Pure quote generation function.

PURE FUNCTION - no I/O, no side effects, no datetime.now(), no random.
All inputs must be passed explicitly, including timestamp and quote_id.
"""
from datetime import datetime
from decimal import Decimal

from .cost_calculator import (
    calculate_delivery_cost,
    calculate_finishing_cost,
    calculate_labor_cost,
    calculate_material_cost,
    calculate_overhead,
)
from .price_book import PriceBook
from .types import CostBreakdown, QuoteParams, QuoteResult, QuoteTier


def generate_quote(
    params: QuoteParams,
    price_book: PriceBook,
    quote_id: str,
    timestamp: datetime,
) -> QuoteResult:
    """
    Generate a quote with 3 pricing tiers.

    PURE FUNCTION - no I/O, no side effects.
    Deterministic: same inputs always produce same outputs.

    Args:
        params: Quote parameters (all Decimal)
        price_book: Frozen pricing data
        quote_id: Quote identifier (for reproducibility tracking)
        timestamp: Quote generation timestamp (injected externally)

    Returns:
        QuoteResult with cost breakdown, tiers, confidence, risk flags
    """
    # Calculate board feet from dimensions
    board_feet = (params.length_in * params.width_in * params.height_in) / Decimal("144")

    # Calculate material cost
    material_cost = calculate_material_cost(
        species=params.wood_species,
        grade=params.material_grade,
        board_feet=board_feet,
        quantity=params.quantity,
        price_book=price_book,
    )

    # Calculate labor costs by department
    installation_hours = params.estimated_labor_hours * Decimal("0.3") if params.installation_required else Decimal("0")
    labor_costs = calculate_labor_cost(
        estimated_hours=params.estimated_labor_hours,
        machine_hours=params.estimated_machine_hours,
        has_woodwork=params.has_woodwork,
        has_metalwork=params.has_metalwork,
        has_finishing=params.has_finishing,
        has_upholstery=params.has_upholstery,
        installation_hours=installation_hours,
        price_book=price_book,
    )
    total_labor = sum(labor_costs.values(), Decimal("0"))

    # Calculate finishing cost
    finish_material_cost = Decimal("0")
    powder_coating_cost = Decimal("0")
    if params.has_finishing or params.has_powder_coating:
        surface_area_sqft = (Decimal("2") * params.length_in * params.width_in) / Decimal("144")
        finish_result = calculate_finishing_cost(
            surface_area_sqft=surface_area_sqft,
            complexity=params.finishing_complexity,
            has_powder_coating=params.has_powder_coating,
            price_book=price_book,
        )
        if isinstance(finish_result, tuple):
            finish_material_cost, powder_coating_cost = finish_result
        else:
            finish_material_cost = finish_result
    finishing_cost = finish_material_cost + powder_coating_cost

    # Calculate delivery cost
    delivery_cost = Decimal("0")
    if params.delivery_miles and params.delivery_miles > Decimal("0"):
        total_bf = board_feet * params.quantity
        is_heavy = total_bf > Decimal("50")
        delivery_cost = calculate_delivery_cost(
            miles=params.delivery_miles,
            is_heavy=is_heavy,
            price_book=price_book,
        )

    # Hardware cost (passed directly from params)
    hardware_cost = params.hardware_cost

    # Complexity adjustment
    complexity_key = str(params.job_complexity_score)
    complexity_multiplier = price_book.complexity_multipliers.get(complexity_key, Decimal("1.0"))
    base_direct = material_cost + total_labor + finishing_cost + hardware_cost + delivery_cost
    complexity_adjustment = base_direct * (complexity_multiplier - Decimal("1"))
    direct_costs = base_direct + complexity_adjustment

    # Calculate overhead
    overhead = calculate_overhead(direct_costs, price_book)

    # Total cost
    total_cost = direct_costs + overhead

    # Apply risk adjustment
    risk_adjustment = Decimal("0")
    if params.risk_adjustment_pct and params.risk_adjustment_pct > Decimal("0"):
        capped_risk = min(
            params.risk_adjustment_pct,
            price_book.max_risk_adjustment_pct * Decimal("100")
        )
        risk_adjustment = total_cost * capped_risk / Decimal("100")
    risk_adjusted_cost = total_cost + risk_adjustment

    # Build cost breakdown using actual CostBreakdown fields
    breakdown = CostBreakdown(
        material_cost=material_cost,
        hardware_cost=hardware_cost,
        finish_material_cost=finish_material_cost,
        powder_coating_cost=powder_coating_cost,
        total_material_cost=material_cost + hardware_cost + finish_material_cost + powder_coating_cost,
        labor_cost_woodwork=labor_costs.get("woodwork", Decimal("0")),
        labor_cost_metalwork=labor_costs.get("metalwork", Decimal("0")),
        labor_cost_finishing=labor_costs.get("finishing", Decimal("0")),
        labor_cost_upholstery=labor_costs.get("upholstery", Decimal("0")),
        labor_cost_machine=labor_costs.get("machine", Decimal("0")),
        labor_cost_installation=labor_costs.get("installation", Decimal("0")),
        total_labor_cost=total_labor,
        delivery_cost=delivery_cost,
        overhead_cost=overhead,
        complexity_adjustment=complexity_adjustment,
        risk_adjustment=risk_adjustment,
        total_direct_cost=direct_costs,
        total_cost=risk_adjusted_cost,
    )

    # Generate 3 pricing tiers (low, standard, premium)
    tier_low, tier_standard, tier_premium = _generate_tiers(risk_adjusted_cost)

    # Calculate confidence score (0-100)
    confidence = _calculate_confidence(params, price_book)

    # Identify risk flags
    risk_flags = _identify_risk_flags(params, breakdown, price_book)

    # Derive confidence level label
    if confidence >= 80:
        confidence_level = "high"
    elif confidence >= 60:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    return QuoteResult(
        cost_breakdown=breakdown,
        tier_low=tier_low,
        tier_standard=tier_standard,
        tier_premium=tier_premium,
        confidence_score=confidence,
        confidence_level=confidence_level,
        risk_flags=risk_flags,
        requires_review=len(risk_flags) > 0 or confidence < 70,
        snapshot_hash=price_book.to_sha256(),
        quote_id=quote_id,
        generated_at=timestamp,
    )


def _generate_tiers(cost: Decimal) -> tuple[QuoteTier, QuoteTier, QuoteTier]:
    """
    Generate 3 pricing tiers from cost basis.

    Low:      15% margin (price = cost / 0.85)
    Standard: 25% margin (price = cost / 0.75)
    Premium:  35% margin (price = cost / 0.65)
    """
    tier_low = QuoteTier(
        name="low",
        price=cost / (Decimal("1") - Decimal("0.15")),
        margin_pct=Decimal("15.0"),
    )
    tier_standard = QuoteTier(
        name="standard",
        price=cost / (Decimal("1") - Decimal("0.25")),
        margin_pct=Decimal("25.0"),
    )
    tier_premium = QuoteTier(
        name="premium",
        price=cost / (Decimal("1") - Decimal("0.35")),
        margin_pct=Decimal("35.0"),
    )
    return (tier_low, tier_standard, tier_premium)


def _calculate_confidence(params: QuoteParams, price_book: PriceBook) -> int:
    """
    Calculate confidence score (0-100) based on input quality.

    High confidence: standard materials, typical complexity, no custom work
    Low confidence: exotic materials, high complexity, custom requirements
    """
    score = 100

    # Penalize exotic materials
    if params.wood_species in ("Walnut", "Cherry", "Other"):
        score -= 10

    # Penalize high complexity
    if params.job_complexity_score >= 4:
        score -= 15

    # Penalize custom/premium grade
    if params.material_grade == "Premium":
        score -= 5

    # Penalize large risk adjustment
    if params.risk_adjustment_pct and params.risk_adjustment_pct > Decimal("10"):
        score -= 10

    # Penalize installation (adds uncertainty)
    if params.installation_required:
        score -= 5

    # Ensure score stays in 0-100 range
    return max(0, min(100, score))


def _identify_risk_flags(
    params: QuoteParams,
    breakdown: CostBreakdown,
    price_book: PriceBook,
) -> tuple[str, ...]:
    """
    Identify risk flags that warrant manual review.

    Returns tuple of risk flag strings (immutable).
    """
    flags = []

    # High complexity
    if params.job_complexity_score >= 4:
        flags.append("HIGH_COMPLEXITY")

    # Large project
    if breakdown.total_cost > Decimal("10000"):
        flags.append("LARGE_PROJECT")

    # Custom/exotic materials
    if params.wood_species == "Other":
        flags.append("CUSTOM_MATERIAL")

    # Significant risk adjustment
    if params.risk_adjustment_pct and params.risk_adjustment_pct > Decimal("15"):
        flags.append("HIGH_RISK_ADJUSTMENT")

    # Long distance delivery (nationwide shipping)
    if params.delivery_miles and params.delivery_miles > Decimal("500"):
        flags.append("NATIONWIDE_DELIVERY")
    elif params.delivery_miles and params.delivery_miles > Decimal("50"):
        flags.append("LONG_DISTANCE_DELIVERY")

    # High labor ratio (labor > 50% of direct costs)
    direct_costs = breakdown.total_material_cost + breakdown.total_labor_cost + breakdown.delivery_cost
    if direct_costs > Decimal("0") and (breakdown.total_labor_cost / direct_costs) > Decimal("0.5"):
        flags.append("HIGH_LABOR_RATIO")

    return tuple(flags)
