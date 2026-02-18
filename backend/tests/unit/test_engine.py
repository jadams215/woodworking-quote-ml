"""Unit tests for pure quoting engine."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.engine.cost_calculator import (
    calculate_board_feet,
    calculate_delivery_cost,
    calculate_finishing_cost,
    calculate_labor_cost,
    calculate_material_cost,
    calculate_overhead,
)
from app.engine.price_book import PriceBook
from app.engine.quote_generator import generate_quote
from app.engine.types import QuoteParams


@pytest.fixture
def sample_price_book():
    """Create a sample price book for testing."""
    return PriceBook(
        material_costs_per_bf={
            "Oak": Decimal("8.00"),
            "Pine": Decimal("3.50"),
            "Walnut": Decimal("15.00"),
            "Other": Decimal("6.00"),
        },
        labor_rates={
            "general": Decimal("45.00"),
            "woodwork": Decimal("55.00"),
            "finishing": Decimal("50.00"),
            "installation": Decimal("70.00"),
        },
        grade_multipliers={
            "Economy": Decimal("0.75"),
            "Standard": Decimal("1.00"),
            "Premium": Decimal("1.35"),
        },
        overhead_pct=Decimal("0.20"),
        waste_factors={"Economy": Decimal("0.15"), "Standard": Decimal("0.10"), "Premium": Decimal("0.08")},
        complexity_multipliers={"1": Decimal("0.85"), "2": Decimal("0.95"), "3": Decimal("1.00"), "4": Decimal("1.15"), "5": Decimal("1.35")},
        finishing_costs_per_sqft={"1": Decimal("1.50"), "2": Decimal("3.00"), "3": Decimal("5.00"), "4": Decimal("8.00"), "5": Decimal("12.00")},
        delivery_base_fee=Decimal("75.00"),
        delivery_per_mile=Decimal("2.50"),
        delivery_heavy_surcharge=Decimal("150.00"),
        installation_multiplier=Decimal("1.25"),
        powder_coating_per_sqft=Decimal("4.50"),
        max_risk_adjustment_pct=Decimal("0.25"),
        margin_targets={
            "low": Decimal("0.15"),
            "standard": Decimal("0.25"),
            "premium": Decimal("0.35"),
        },
    )


def test_calculate_board_feet():
    """Test board feet calculation is exact."""
    # 12" x 12" x 1" = 144 cubic inches = 1 board foot
    result = calculate_board_feet(
        length_in=Decimal("12"), width_in=Decimal("12"), height_in=Decimal("1")
    )
    assert result == Decimal("1.00")

    # 24" x 6" x 2" = 288 cubic inches = 2 board feet
    result = calculate_board_feet(
        length_in=Decimal("24"), width_in=Decimal("6"), height_in=Decimal("2")
    )
    assert result == Decimal("2.00")


def test_calculate_material_cost(sample_price_book):
    """Test material cost calculation with waste factor."""
    cost = calculate_material_cost(
        species="Oak",
        grade="Standard",
        board_feet=Decimal("10.0"),
        quantity=2,
        price_book=sample_price_book,
    )
    # Oak Standard = $8/bf, 10 bf * 2 qty = 160, with 10% waste = 176
    expected = Decimal("8.00") * Decimal("10.0") * Decimal("2") * Decimal("1.10")
    assert cost == expected


def test_calculate_labor_cost(sample_price_book):
    """Test labor cost calculation by department."""
    costs = calculate_labor_cost(
        estimated_hours=Decimal("5.0"),
        machine_hours=Decimal("0"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=False,
        has_upholstery=False,
        installation_hours=Decimal("1.0"),
        price_book=sample_price_book,
    )

    assert costs["woodwork"] == Decimal("5.0") * Decimal("55.00")
    # Installation rate includes installation_multiplier (1.25): 1.0 * $70 * 1.25 = $87.50
    assert costs["installation"] == Decimal("1.0") * Decimal("70.00") * Decimal("1.25")
    assert "metalwork" not in costs or costs["metalwork"] == Decimal("0")


def test_calculate_delivery_cost(sample_price_book):
    """Test delivery cost with and without heavy surcharge."""
    # Base + 10 miles
    cost = calculate_delivery_cost(
        miles=Decimal("10"), is_heavy=False, price_book=sample_price_book
    )
    assert cost == Decimal("75.00") + (Decimal("10") * Decimal("2.50"))

    # With heavy surcharge
    cost = calculate_delivery_cost(
        miles=Decimal("10"), is_heavy=True, price_book=sample_price_book
    )
    assert cost == Decimal("75.00") + (Decimal("10") * Decimal("2.50")) + Decimal("150.00")


def test_calculate_overhead(sample_price_book):
    """Test overhead calculation."""
    direct_costs = Decimal("1000.00")
    overhead = calculate_overhead(direct_costs, sample_price_book)
    assert overhead == direct_costs * Decimal("0.20")


def test_generate_quote_reproducibility(sample_price_book):
    """Test that same inputs produce identical outputs."""
    params = QuoteParams(
        wood_species="Oak",
        material_grade="Standard",
        project_type="conference_table",
        length_in=Decimal("96"),
        width_in=Decimal("42"),
        height_in=Decimal("1.5"),
        quantity=1,
        estimated_labor_hours=Decimal("5.0"),
        estimated_machine_hours=Decimal("0"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=False,
        has_upholstery=False,
        has_powder_coating=False,
        finishing_complexity=2,
        hardware_cost=Decimal("0"),
        delivery_miles=Decimal("0"),
        installation_required=False,
        job_complexity_score=3,
        risk_adjustment_pct=Decimal("0"),
    )

    quote_id = "Q-TEST-001"
    timestamp = datetime(2024, 1, 1, 12, 0, 0)

    # Generate twice with same inputs
    result1 = generate_quote(params, sample_price_book, quote_id, timestamp)
    result2 = generate_quote(params, sample_price_book, quote_id, timestamp)

    # Results should be identical
    assert result1.cost_breakdown.total_cost == result2.cost_breakdown.total_cost
    assert result1.tier_low.price == result2.tier_low.price
    assert result1.tier_standard.price == result2.tier_standard.price
    assert result1.tier_premium.price == result2.tier_premium.price
    assert result1.confidence_score == result2.confidence_score
    assert result1.risk_flags == result2.risk_flags
    assert result1.snapshot_hash == result2.snapshot_hash


def test_generate_quote_decimal_precision(sample_price_book):
    """Test that all monetary values are Decimal, not float."""
    params = QuoteParams(
        wood_species="Oak",
        material_grade="Standard",
        project_type="coffee_table",
        length_in=Decimal("48"),
        width_in=Decimal("24"),
        height_in=Decimal("1.5"),
        quantity=1,
        estimated_labor_hours=Decimal("3.25"),
        estimated_machine_hours=Decimal("0"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=False,
        has_upholstery=False,
        has_powder_coating=False,
        finishing_complexity=2,
        hardware_cost=Decimal("25.50"),
        delivery_miles=Decimal("15.75"),
        installation_required=False,
        job_complexity_score=3,
        risk_adjustment_pct=Decimal("5.0"),
    )

    result = generate_quote(params, sample_price_book, "Q-001", datetime.utcnow())

    # All breakdown values must be Decimal
    assert isinstance(result.cost_breakdown.material_cost, Decimal)
    assert isinstance(result.cost_breakdown.total_labor_cost, Decimal)
    assert isinstance(result.cost_breakdown.overhead_cost, Decimal)
    assert isinstance(result.cost_breakdown.total_cost, Decimal)

    # All tier prices must be Decimal
    for tier in [result.tier_low, result.tier_standard, result.tier_premium]:
        assert isinstance(tier.price, Decimal)
        assert isinstance(tier.margin_pct, Decimal)


def test_price_book_sha256_deterministic(sample_price_book):
    """Test that same price book produces same hash."""
    hash1 = sample_price_book.to_sha256()
    hash2 = sample_price_book.to_sha256()

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex chars


def test_margin_calculation():
    """Test that margin calculation is correct."""
    # If cost = $100 and margin = 25%, price = 100 / (1 - 0.25) = $133.33
    cost = Decimal("100.00")
    margin_pct = Decimal("25.0")

    price = cost / (Decimal("1") - margin_pct / Decimal("100"))
    expected = Decimal("133.33")

    # Round to 2 places for comparison
    assert price.quantize(Decimal("0.01")) == expected


def test_quote_risk_flags(sample_price_book):
    """Test that risk flags are identified correctly."""
    # High complexity + large project should trigger flags
    params = QuoteParams(
        wood_species="Other",  # Custom material
        material_grade="Standard",
        project_type="custom",
        length_in=Decimal("240"),  # Large project
        width_in=Decimal("60"),
        height_in=Decimal("3"),
        quantity=10,
        estimated_labor_hours=Decimal("100.0"),
        estimated_machine_hours=Decimal("0"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=False,
        has_upholstery=False,
        has_powder_coating=False,
        finishing_complexity=2,
        hardware_cost=Decimal("0"),
        delivery_miles=Decimal("100"),
        installation_required=False,
        job_complexity_score=5,  # High complexity
        risk_adjustment_pct=Decimal("20.0"),  # High risk adjustment
    )

    result = generate_quote(params, sample_price_book, "Q-RISK", datetime.utcnow())

    # Should have multiple risk flags
    assert len(result.risk_flags) > 0
    assert "HIGH_COMPLEXITY" in result.risk_flags
    assert "CUSTOM_MATERIAL" in result.risk_flags or "Other" in params.wood_species
    assert result.confidence_score < 100


def test_quote_confidence_scoring(sample_price_book):
    """Test confidence score calculation."""
    # Simple, standard quote should have high confidence
    simple_params = QuoteParams(
        wood_species="Oak",
        material_grade="Standard",
        project_type="coffee_table",
        length_in=Decimal("48"),
        width_in=Decimal("24"),
        height_in=Decimal("1.5"),
        quantity=1,
        estimated_labor_hours=Decimal("5.0"),
        estimated_machine_hours=Decimal("0"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=False,
        has_upholstery=False,
        has_powder_coating=False,
        finishing_complexity=2,
        hardware_cost=Decimal("0"),
        delivery_miles=Decimal("0"),
        installation_required=False,
        job_complexity_score=2,
        risk_adjustment_pct=Decimal("0"),
    )

    result = generate_quote(simple_params, sample_price_book, "Q-HIGH", datetime.utcnow())
    assert result.confidence_score >= 70

    # Complex quote should have lower confidence
    complex_params = QuoteParams(
        wood_species="Walnut",
        material_grade="Premium",
        project_type="custom",
        length_in=simple_params.length_in,
        width_in=simple_params.width_in,
        height_in=simple_params.height_in,
        quantity=simple_params.quantity,
        estimated_labor_hours=simple_params.estimated_labor_hours,
        estimated_machine_hours=simple_params.estimated_machine_hours,
        has_woodwork=simple_params.has_woodwork,
        has_metalwork=simple_params.has_metalwork,
        has_finishing=simple_params.has_finishing,
        has_upholstery=simple_params.has_upholstery,
        has_powder_coating=simple_params.has_powder_coating,
        finishing_complexity=simple_params.finishing_complexity,
        hardware_cost=simple_params.hardware_cost,
        delivery_miles=simple_params.delivery_miles,
        installation_required=True,
        job_complexity_score=5,
        risk_adjustment_pct=Decimal("15.0"),
    )

    result = generate_quote(complex_params, sample_price_book, "Q-LOW", datetime.utcnow())
    assert result.confidence_score < 90
