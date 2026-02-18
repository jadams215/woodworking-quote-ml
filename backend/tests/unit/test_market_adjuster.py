"""Unit tests for the pure MarketMultipliers engine module.

These tests verify:
1. MarketMultipliers construction, serialization, and round-trip
2. All pure adjustment functions
3. Integration with calculate_total_cost (with and without market data)
4. Identity multipliers produce no change
"""

from datetime import date
from decimal import Decimal

import pytest

from app.engine.market_adjuster import (
    MarketMultipliers,
    apply_demand_premium,
    apply_fuel_surcharge,
    apply_labor_market_adjustment,
    apply_material_market_adjustment,
    apply_powder_coating_adjustment,
)
from app.engine.cost_calculator import calculate_total_cost
from app.engine.price_book import PriceBook
from app.engine.types import QuoteParams


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_market() -> MarketMultipliers:
    """Market multipliers with known adjustment values."""
    return MarketMultipliers(
        material_multipliers={
            "Walnut:FAS": Decimal("1.15"),
            "Oak:Standard": Decimal("0.95"),
        },
        labor_multiplier=Decimal("1.10"),
        fuel_surcharge_factor=Decimal("1.05"),
        demand_premium_factor=Decimal("1.08"),
        powder_coating_multiplier=Decimal("0.90"),
        subcontractor_multiplier=Decimal("1.00"),
        snapshot_date=date(2026, 2, 16),
    )


@pytest.fixture
def identity_market() -> MarketMultipliers:
    return MarketMultipliers.identity()


@pytest.fixture
def price_book() -> PriceBook:
    return PriceBook.from_snapshot_data({
        "material_costs_per_bf": {"Walnut": "15.00", "Oak": "8.00", "Other": "6.00"},
        "grade_multipliers": {"Economy": "0.75", "Standard": "1.00", "Premium": "1.35"},
        "waste_factors": {"Economy": "0.15", "Standard": "0.10", "Premium": "0.08"},
        "labor_rates": {
            "general": "45.00", "woodwork": "55.00", "metalwork": "60.00",
            "finishing": "50.00", "upholstery": "65.00", "installation": "70.00",
            "machine": "40.00",
        },
        "finishing_costs_per_sqft": {"1": "1.50", "2": "3.00", "3": "5.00", "4": "8.00", "5": "12.00"},
        "overhead_pct": "0.20",
        "installation_multiplier": "1.25",
        "powder_coating_per_sqft": "4.50",
        "max_risk_adjustment_pct": "0.25",
        "complexity_multipliers": {"1": "0.85", "2": "0.95", "3": "1.00", "4": "1.15", "5": "1.35"},
        "delivery": {"base_fee": "75.00", "per_mile": "2.50", "heavy_surcharge": "150.00"},
        "margin_targets": {"low": "15.00", "standard": "25.00", "premium": "35.00"},
    })


@pytest.fixture
def sample_params() -> QuoteParams:
    return QuoteParams(
        length_in=Decimal("60"),
        width_in=Decimal("24"),
        height_in=Decimal("30"),
        quantity=1,
        wood_species="Walnut",
        material_grade="Standard",
        project_type="credenza",
        estimated_labor_hours=Decimal("10"),
        estimated_machine_hours=Decimal("2"),
        has_woodwork=True,
        has_metalwork=False,
        has_finishing=True,
        has_upholstery=False,
        has_powder_coating=False,
        finishing_complexity=3,
        hardware_cost=Decimal("50"),
        delivery_miles=Decimal("15"),
        installation_required=False,
        job_complexity_score=3,
        risk_adjustment_pct=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# MarketMultipliers construction
# ---------------------------------------------------------------------------

class TestMarketMultipliersConstruction:

    def test_identity_all_ones(self, identity_market):
        assert identity_market.labor_multiplier == Decimal("1")
        assert identity_market.fuel_surcharge_factor == Decimal("1")
        assert identity_market.demand_premium_factor == Decimal("1")
        assert identity_market.powder_coating_multiplier == Decimal("1")
        assert identity_market.material_multipliers == {}

    def test_frozen(self, sample_market):
        with pytest.raises(AttributeError):
            sample_market.labor_multiplier = Decimal("2")

    def test_material_lookup_exact_match(self, sample_market):
        assert sample_market.material_multiplier("Walnut", "FAS") == Decimal("1.15")

    def test_material_lookup_species_fallback(self, sample_market):
        # "Walnut:Premium" not in dict, falls back to first "Walnut:*"
        assert sample_market.material_multiplier("Walnut", "Premium") == Decimal("1.15")

    def test_material_lookup_missing_returns_one(self, sample_market):
        assert sample_market.material_multiplier("Pine", "Standard") == Decimal("1")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:

    def test_to_dict_round_trip(self, sample_market):
        d = sample_market.to_dict()
        restored = MarketMultipliers.from_snapshot_data(d)
        assert restored.labor_multiplier == sample_market.labor_multiplier
        assert restored.fuel_surcharge_factor == sample_market.fuel_surcharge_factor
        assert restored.material_multipliers == sample_market.material_multipliers
        assert restored.snapshot_date == sample_market.snapshot_date

    def test_sha256_deterministic(self, sample_market):
        h1 = sample_market.to_sha256()
        h2 = sample_market.to_sha256()
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_changes_with_data(self, sample_market, identity_market):
        assert sample_market.to_sha256() != identity_market.to_sha256()


# ---------------------------------------------------------------------------
# Pure adjustment functions
# ---------------------------------------------------------------------------

class TestAdjustmentFunctions:

    def test_material_adjustment_applies(self, sample_market):
        base = Decimal("100")
        adjusted = apply_material_market_adjustment(base, "Walnut", "FAS", sample_market)
        assert adjusted == Decimal("115.00")

    def test_material_adjustment_none_market(self):
        base = Decimal("100")
        assert apply_material_market_adjustment(base, "Walnut", "FAS", None) == base

    def test_labor_adjustment(self, sample_market):
        base = Decimal("500")
        adjusted = apply_labor_market_adjustment(base, sample_market)
        assert adjusted == Decimal("550.0")

    def test_labor_adjustment_none(self):
        assert apply_labor_market_adjustment(Decimal("500"), None) == Decimal("500")

    def test_fuel_surcharge(self, sample_market):
        base = Decimal("200")
        adjusted = apply_fuel_surcharge(base, sample_market)
        assert adjusted == Decimal("210.00")

    def test_powder_coating_adjustment(self, sample_market):
        base = Decimal("100")
        adjusted = apply_powder_coating_adjustment(base, sample_market)
        assert adjusted == Decimal("90.0")

    def test_demand_premium(self, sample_market):
        margin = Decimal("25")
        adjusted = apply_demand_premium(margin, sample_market)
        # 25 + 25 * (1.08 - 1) = 25 + 2 = 27
        assert adjusted == Decimal("27.00")

    def test_demand_premium_identity(self, identity_market):
        margin = Decimal("25")
        assert apply_demand_premium(margin, identity_market) == Decimal("25")


# ---------------------------------------------------------------------------
# Integration: calculate_total_cost with market multipliers
# ---------------------------------------------------------------------------

class TestCalculateTotalCostWithMarket:

    def test_no_market_backward_compatible(self, sample_params, price_book):
        """calculate_total_cost without market param works as before."""
        breakdown = calculate_total_cost(sample_params, price_book)
        assert breakdown.total_cost > Decimal("0")

    def test_identity_market_same_as_none(self, sample_params, price_book, identity_market):
        """Identity multipliers produce the same result as no market."""
        without = calculate_total_cost(sample_params, price_book)
        with_identity = calculate_total_cost(sample_params, price_book, identity_market)
        assert without.total_cost == with_identity.total_cost

    def test_market_increases_cost(self, sample_params, price_book, sample_market):
        """When multipliers > 1, total cost increases."""
        without = calculate_total_cost(sample_params, price_book)
        with_market = calculate_total_cost(sample_params, price_book, sample_market)
        # Material (Walnut 1.15x) and labor (1.10x) should push cost up
        assert with_market.total_cost > without.total_cost

    def test_market_adjusts_material_cost(self, sample_params, price_book, sample_market):
        """Material cost is adjusted by the Walnut multiplier."""
        without = calculate_total_cost(sample_params, price_book)
        with_market = calculate_total_cost(sample_params, price_book, sample_market)
        assert with_market.material_cost > without.material_cost

    def test_market_adjusts_labor_cost(self, sample_params, price_book, sample_market):
        """Labor costs are adjusted by the labor multiplier."""
        without = calculate_total_cost(sample_params, price_book)
        with_market = calculate_total_cost(sample_params, price_book, sample_market)
        assert with_market.total_labor_cost > without.total_labor_cost

    def test_market_adjusts_delivery_cost(self, sample_params, price_book, sample_market):
        """Delivery cost is adjusted by the fuel surcharge factor."""
        without = calculate_total_cost(sample_params, price_book)
        with_market = calculate_total_cost(sample_params, price_book, sample_market)
        assert with_market.delivery_cost > without.delivery_cost
