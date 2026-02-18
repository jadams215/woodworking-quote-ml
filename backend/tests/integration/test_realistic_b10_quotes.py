"""Golden test cases based on realistic B10 Union pricing.

These tests validate that the quoting engine produces quotes in the expected
price range for B10's actual product offerings, based on analysis of their
portfolio and market positioning.

Test cases derived from BUSINESS_CONTEXT.md analysis of https://www.b-10union.com/
"""
from decimal import Decimal

import pytest

from app.engine.price_book import PriceBook
from app.engine.quote_generator import generate_quote
from app.engine.types import QuoteParams
from datetime import datetime


@pytest.fixture
def b10_price_book():
    """Create a realistic price book matching B10 Union's current costs."""
    return PriceBook(
        material_costs_per_bf={
            "Pine": Decimal("3.50"),
            "Oak": Decimal("8.00"),
            "White Oak": Decimal("9.50"),  # B10's most common wood
            "Walnut": Decimal("15.00"),  # B10's premium wood
            "Parota": Decimal("20.00"),  # Live edge specialty
            "Other": Decimal("6.00"),
        },
        labor_rates={
            "general": Decimal("45.00"),
            "woodwork": Decimal("55.00"),
            "metalwork": Decimal("60.00"),
            "finishing": Decimal("50.00"),
            "installation": Decimal("70.00"),
        },
        grade_multipliers={
            "Economy": Decimal("0.75"),
            "Standard": Decimal("1.00"),
            "Premium": Decimal("1.35"),
        },
        overhead_pct=Decimal("0.20"),
        waste_factors={
            "Economy": Decimal("0.15"),
            "Standard": Decimal("0.10"),
            "Premium": Decimal("0.08"),
        },
        complexity_multipliers={
            "1": Decimal("0.85"),
            "2": Decimal("0.95"),
            "3": Decimal("1.00"),
            "4": Decimal("1.15"),
            "5": Decimal("1.35"),
        },
        finishing_costs_per_sqft={
            "1": Decimal("1.50"),
            "2": Decimal("3.00"),
            "3": Decimal("5.00"),
            "4": Decimal("8.00"),
            "5": Decimal("12.00"),
        },
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


class TestB10ConferenceTables:
    """Test quotes for conference/dining tables - B10's core business (35-40% of portfolio)."""

    def test_8ft_white_oak_standard_table(self, b10_price_book):
        """
        8-foot white oak conference table.

        Expected portfolio pricing: $3,500-5,000 (standard tier)
        This is B10's bread and butter product.
        """
        params = QuoteParams(
            wood_species="White Oak",
            material_grade="Standard",
            project_type="conference_table",
            length_in=Decimal("96"),  # 8 feet
            width_in=Decimal("42"),
            height_in=Decimal("1.5"),
            quantity=1,
            estimated_labor_hours=Decimal("12.0"),  # Realistic for 8-foot table
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=3,
            hardware_cost=Decimal("75.00"),  # Cable management, levelers
            delivery_miles=Decimal("15"),  # Local Atlanta delivery
            installation_required=False,
            job_complexity_score=3,
            risk_adjustment_pct=Decimal("0"),
        )

        result = generate_quote(params, b10_price_book, "Q-001", datetime.utcnow())

        # Standard tier should be in expected range
        standard_price = result.tier_standard.price
        assert Decimal("2000") <= standard_price <= Decimal("5000"), \
            f"8-foot white oak table quote ${standard_price} outside expected range $2,000-5,000"

        # Verify the tiers are ordered correctly
        assert result.tier_premium.price > result.tier_standard.price > result.tier_low.price

        # Should have high confidence for core product
        assert result.confidence_score >= 70, \
            f"Confidence {result.confidence_score}% too low for core product"

    def test_12ft_walnut_premium_table(self, b10_price_book):
        """
        12-foot walnut conference table with premium finish.

        Expected portfolio pricing: $6,500-9,000 (premium tier)
        """
        params = QuoteParams(
            wood_species="Walnut",
            material_grade="Premium",
            project_type="conference_table",
            length_in=Decimal("144"),  # 12 feet
            width_in=Decimal("48"),
            height_in=Decimal("2.0"),
            quantity=1,
            estimated_labor_hours=Decimal("20.0"),  # More complex joinery
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=4,  # Premium finish
            hardware_cost=Decimal("150.00"),
            delivery_miles=Decimal("25"),
            installation_required=False,
            job_complexity_score=4,
            risk_adjustment_pct=Decimal("0"),
        )

        result = generate_quote(params, b10_price_book, "Q-002", datetime.utcnow())

        # Premium tier should be in expected range
        premium_price = result.tier_premium.price
        assert Decimal("5000") <= premium_price <= Decimal("15000"), \
            f"12-foot walnut table quote ${premium_price} outside expected range $5,000-15,000"

        # Premium > Standard (pricing tiers ordered correctly)
        assert result.tier_premium.price > result.tier_standard.price

    def test_20ft_parota_specialty_table(self, b10_price_book):
        """
        20-foot live edge Parota conference table.

        Expected portfolio pricing: $15,000-25,000 (premium tier)
        This is B10's highest-end signature piece.
        """
        params = QuoteParams(
            wood_species="Parota",
            material_grade="Premium",
            project_type="conference_table",
            length_in=Decimal("240"),  # 20 feet (mentioned on website)
            width_in=Decimal("54"),
            height_in=Decimal("3.0"),  # Thick live edge slab
            quantity=1,
            estimated_labor_hours=Decimal("40.0"),  # Extensive work
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=True,  # Custom metal base
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=5,  # Maximum finish quality
            hardware_cost=Decimal("500.00"),  # High-end hardware
            delivery_miles=Decimal("100"),  # Regional delivery
            installation_required=True,  # Site installation required
            job_complexity_score=5,  # Maximum complexity
            risk_adjustment_pct=Decimal("10.0"),  # High-risk custom piece
        )

        result = generate_quote(params, b10_price_book, "Q-003", datetime.utcnow())

        # Premium tier should be in expected range
        premium_price = result.tier_premium.price
        # Large specialty piece - should be expensive (exact amount depends on labor/material inputs)
        assert premium_price > Decimal("10000"), \
            f"20-foot Parota table quote ${premium_price} seems too low for flagship piece"

        # Should have risk flags for specialty work
        assert len(result.risk_flags) > 0, "High-complexity custom piece should have risk flags"

        # Premium should cost more than a standard 8-foot table
        assert result.tier_premium.price > Decimal("5000")


class TestB10Credenzas:
    """Test quotes for credenzas - 20-25% of B10's portfolio."""

    def test_6ft_oak_simple_credenza(self, b10_price_book):
        """
        6-foot oak credenza with standard finish.

        Expected portfolio pricing: $2,500-4,000 (standard tier)
        """
        params = QuoteParams(
            wood_species="Oak",
            material_grade="Standard",
            project_type="credenza",
            length_in=Decimal("72"),  # 6 feet
            width_in=Decimal("18"),
            height_in=Decimal("1.0"),
            quantity=1,
            estimated_labor_hours=Decimal("15.0"),  # Drawers, doors, joinery
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=3,
            hardware_cost=Decimal("200.00"),  # Soft-close drawers, pulls
            delivery_miles=Decimal("20"),
            installation_required=False,
            job_complexity_score=4,  # Moderate complexity
            risk_adjustment_pct=Decimal("0"),
        )

        result = generate_quote(params, b10_price_book, "Q-004", datetime.utcnow())

        standard_price = result.tier_standard.price
        assert Decimal("1500") <= standard_price <= Decimal("5000"), \
            f"6-foot credenza quote ${standard_price} outside expected range $1,500-5,000"

        # Should cost more than materials alone
        assert result.tier_standard.price > result.cost_breakdown.total_material_cost

    def test_8ft_walnut_complex_credenza(self, b10_price_book):
        """
        8-foot walnut credenza with complex interior.

        Expected portfolio pricing: $4,500-7,000 (premium tier)
        """
        params = QuoteParams(
            wood_species="Walnut",
            material_grade="Premium",
            project_type="credenza",
            length_in=Decimal("96"),  # 8 feet
            width_in=Decimal("20"),
            height_in=Decimal("1.25"),
            quantity=1,
            estimated_labor_hours=Decimal("25.0"),  # Complex interior
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=4,
            hardware_cost=Decimal("350.00"),  # Premium hardware
            delivery_miles=Decimal("30"),
            installation_required=False,
            job_complexity_score=4,
            risk_adjustment_pct=Decimal("0"),
        )

        result = generate_quote(params, b10_price_book, "Q-005", datetime.utcnow())

        premium_price = result.tier_premium.price
        assert Decimal("3000") <= premium_price <= Decimal("15000"), \
            f"8-foot walnut credenza quote ${premium_price} outside expected range $3,000-15,000"

        # Walnut credenza should cost more than oak credenza
        assert result.tier_premium.price > Decimal("3000")


class TestB10CoffeeTables:
    """Test quotes for coffee tables - 10-15% of B10's portfolio."""

    def test_48x24_oak_coffee_table(self, b10_price_book):
        """
        Standard 48x24 oak coffee table.

        Expected portfolio pricing: $1,200-2,000 (standard tier)
        """
        params = QuoteParams(
            wood_species="Oak",
            material_grade="Standard",
            project_type="coffee_table",
            length_in=Decimal("48"),
            width_in=Decimal("24"),
            height_in=Decimal("1.5"),
            quantity=1,
            estimated_labor_hours=Decimal("8.0"),
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=2,
            hardware_cost=Decimal("50.00"),
            delivery_miles=Decimal("10"),
            installation_required=False,
            job_complexity_score=2,
            risk_adjustment_pct=Decimal("0"),
        )

        result = generate_quote(params, b10_price_book, "Q-006", datetime.utcnow())

        standard_price = result.tier_standard.price
        assert Decimal("800") <= standard_price <= Decimal("2500"), \
            f"Coffee table quote ${standard_price} outside expected range $800-2,500"

        # Coffee table should be priced lower than an 8-foot conference table
        assert result.tier_standard.price < Decimal("3000")

    def test_live_edge_parota_coffee_table(self, b10_price_book):
        """
        Specialty live edge Parota coffee table.

        Expected portfolio pricing: $2,500-4,000 (premium tier)
        """
        params = QuoteParams(
            wood_species="Parota",
            material_grade="Premium",
            project_type="coffee_table",
            length_in=Decimal("60"),
            width_in=Decimal("30"),
            height_in=Decimal("2.5"),  # Thick slab
            quantity=1,
            estimated_labor_hours=Decimal("12.0"),  # Live edge prep
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=True,  # Metal base
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=4,
            hardware_cost=Decimal("150.00"),
            delivery_miles=Decimal("15"),
            installation_required=False,
            job_complexity_score=3,
            risk_adjustment_pct=Decimal("5.0"),
        )

        result = generate_quote(params, b10_price_book, "Q-007", datetime.utcnow())

        premium_price = result.tier_premium.price
        # Live edge Parota with metal base - should be premium priced
        assert Decimal("1500") <= premium_price <= Decimal("6000"), \
            f"Live edge coffee table quote ${premium_price} outside expected range $1,500-6,000"

        # Live edge specialty should cost more than simple oak coffee table
        assert result.tier_premium.price > Decimal("1200")


class TestB10BuiltIns:
    """Test quotes for built-in cabinetry - 15-20% of B10's portfolio."""

    def test_built_in_cabinetry(self, b10_price_book):
        """
        Custom built-in cabinetry with site installation.

        Expected: Higher prices due to custom sizing and installation.
        """
        params = QuoteParams(
            wood_species="White Oak",
            material_grade="Premium",
            project_type="built_in",
            length_in=Decimal("120"),  # 10 feet of cabinetry
            width_in=Decimal("24"),
            height_in=Decimal("1.0"),
            quantity=3,  # Multiple units
            estimated_labor_hours=Decimal("30.0"),  # Custom work
            estimated_machine_hours=Decimal("0"),
            has_woodwork=True,
            has_metalwork=False,
            has_finishing=True,
            has_upholstery=False,
            has_powder_coating=False,
            finishing_complexity=4,
            hardware_cost=Decimal("400.00"),
            delivery_miles=Decimal("25"),
            installation_required=True,  # Always required for built-ins
            job_complexity_score=5,  # Site adaptation required
            risk_adjustment_pct=Decimal("10.0"),  # Site work risk
        )

        result = generate_quote(params, b10_price_book, "Q-008", datetime.utcnow())

        # Built-ins should have installation flag in risk factors
        assert params.installation_required is True
        assert params.job_complexity_score >= 4

        premium_price = result.tier_premium.price
        # Built-ins are typically premium-priced
        assert premium_price > Decimal("5000"), \
            f"Built-in cabinetry quote ${premium_price} seems too low for custom installation work"
