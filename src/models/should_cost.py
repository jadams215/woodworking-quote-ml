"""
Deterministic Should-Cost Model for Woodworking Quotes.

This module implements a bottom-up cost model based on:
- Material costs (wood, hardware, finish materials)
- Labor costs (hourly rates by skill level)
- Overhead allocation
- Delivery and installation
- Margin targets

All cost tables are configurable via JSON/YAML for easy updates
without code changes.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum


# Default cost tables (can be overridden via config file)
DEFAULT_COST_TABLES = {
    # Material costs per board foot by species
    "material_costs_per_bf": {
        "Pine": 3.50,
        "MDF": 2.00,
        "Plywood": 4.00,
        "Oak": 8.00,
        "Maple": 9.00,
        "Cherry": 12.00,
        "Walnut": 15.00,
        "Other": 6.00,
    },

    # Material grade multipliers
    "grade_multipliers": {
        "Economy": 0.75,
        "Standard": 1.00,
        "Premium": 1.35,
    },

    # Labor rates per hour by department/skill
    "labor_rates": {
        "general": 45.00,
        "woodwork": 55.00,
        "metalwork": 60.00,
        "finishing": 50.00,
        "upholstery": 65.00,
        "installation": 70.00,
        "machine": 40.00,  # Machine time (lower direct labor)
    },

    # Finishing costs per square foot
    "finishing_costs_per_sqft": {
        1: 1.50,   # Minimal - raw or simple clear coat
        2: 3.00,   # Basic - single color
        3: 5.00,   # Moderate - multiple colors
        4: 8.00,   # Complex - custom finishes
        5: 12.00,  # Elaborate - specialty finishes
    },

    # Powder coating cost per square foot
    "powder_coating_per_sqft": 4.50,

    # Hardware cost categories
    "hardware_base_costs": {
        "minimal": 25.00,
        "standard": 75.00,
        "premium": 150.00,
        "custom": 300.00,
    },

    # Delivery costs
    "delivery": {
        "base_fee": 75.00,
        "per_mile": 2.50,
        "heavy_item_surcharge": 150.00,  # Items over 200 lbs
    },

    # Installation labor multiplier (vs standard labor)
    "installation_multiplier": 1.25,

    # Overhead allocation as percentage of direct costs
    "overhead_pct": 0.20,

    # Waste factor by material grade
    "waste_factors": {
        "Economy": 0.15,
        "Standard": 0.10,
        "Premium": 0.08,
    },

    # Risk adjustment caps
    "max_risk_adjustment_pct": 0.25,

    # Complexity multipliers
    "complexity_multipliers": {
        1: 0.85,  # Very simple
        2: 0.95,  # Simple
        3: 1.00,  # Standard
        4: 1.15,  # Complex
        5: 1.35,  # Very complex
    },
}


@dataclass
class CostBreakdown:
    """Detailed breakdown of all cost components."""
    # Direct costs
    material_cost: float = 0.0
    hardware_cost: float = 0.0
    finish_material_cost: float = 0.0
    powder_coating_cost: float = 0.0

    # Labor costs
    labor_cost_woodwork: float = 0.0
    labor_cost_metalwork: float = 0.0
    labor_cost_finishing: float = 0.0
    labor_cost_upholstery: float = 0.0
    labor_cost_machine: float = 0.0
    labor_cost_installation: float = 0.0

    # Indirect costs
    overhead_cost: float = 0.0
    delivery_cost: float = 0.0

    # Adjustments
    waste_adjustment: float = 0.0
    complexity_adjustment: float = 0.0
    risk_adjustment: float = 0.0

    # Totals
    total_material_cost: float = 0.0
    total_labor_cost: float = 0.0
    total_direct_cost: float = 0.0
    total_cost: float = 0.0

    # Calculated after margins
    suggested_price: float = 0.0
    gross_margin_pct: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            'material_cost': self.material_cost,
            'hardware_cost': self.hardware_cost,
            'finish_material_cost': self.finish_material_cost,
            'powder_coating_cost': self.powder_coating_cost,
            'labor_cost_woodwork': self.labor_cost_woodwork,
            'labor_cost_metalwork': self.labor_cost_metalwork,
            'labor_cost_finishing': self.labor_cost_finishing,
            'labor_cost_upholstery': self.labor_cost_upholstery,
            'labor_cost_machine': self.labor_cost_machine,
            'labor_cost_installation': self.labor_cost_installation,
            'overhead_cost': self.overhead_cost,
            'delivery_cost': self.delivery_cost,
            'waste_adjustment': self.waste_adjustment,
            'complexity_adjustment': self.complexity_adjustment,
            'risk_adjustment': self.risk_adjustment,
            'total_material_cost': self.total_material_cost,
            'total_labor_cost': self.total_labor_cost,
            'total_direct_cost': self.total_direct_cost,
            'total_cost': self.total_cost,
            'suggested_price': self.suggested_price,
            'gross_margin_pct': self.gross_margin_pct,
        }


class ShouldCostModel:
    """
    Deterministic cost model for woodworking quotes.

    Calculates a bottom-up cost estimate based on:
    - Material and hardware costs
    - Labor hours by department
    - Finishing complexity
    - Delivery and installation
    - Overhead allocation
    - Risk adjustments
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the should-cost model.

        Args:
            config_path: Optional path to JSON config file with cost tables
        """
        self.cost_tables = DEFAULT_COST_TABLES.copy()

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load cost tables from config file."""
        with open(config_path, 'r') as f:
            custom_config = json.load(f)

        # Deep merge with defaults
        for key, value in custom_config.items():
            if key in self.cost_tables and isinstance(value, dict):
                self.cost_tables[key].update(value)
            else:
                self.cost_tables[key] = value

    def save_config(self, config_path: Path) -> None:
        """Save current cost tables to config file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(self.cost_tables, f, indent=2)

    def calculate_material_cost(
        self,
        wood_species: str,
        material_grade: str,
        length_in: float,
        width_in: float,
        height_in: float,
        quantity: int = 1
    ) -> float:
        """
        Calculate material cost based on dimensions and species.

        Uses board feet calculation: (L x W x T) / 144
        """
        # Convert dimensions to board feet
        # Assuming height is thickness for standard calculations
        board_feet = (length_in * width_in * height_in) / 144.0

        # Get cost per board foot
        species_cost = self.cost_tables["material_costs_per_bf"].get(
            wood_species,
            self.cost_tables["material_costs_per_bf"]["Other"]
        )

        # Apply grade multiplier
        grade_mult = self.cost_tables["grade_multipliers"].get(
            material_grade,
            self.cost_tables["grade_multipliers"]["Standard"]
        )

        # Apply waste factor
        waste_factor = self.cost_tables["waste_factors"].get(
            material_grade,
            self.cost_tables["waste_factors"]["Standard"]
        )

        base_cost = board_feet * species_cost * grade_mult * quantity
        waste_cost = base_cost * waste_factor

        return base_cost + waste_cost

    def calculate_labor_cost(
        self,
        estimated_labor_hours: float,
        estimated_machine_hours: float = 0,
        has_woodwork: bool = True,
        has_metalwork: bool = False,
        has_finishing: bool = True,
        has_upholstery: bool = False,
        installation_hours: float = 0
    ) -> Dict[str, float]:
        """
        Calculate labor costs by department.

        Returns breakdown of labor costs.
        """
        rates = self.cost_tables["labor_rates"]
        labor_costs = {}

        # Distribute labor hours across departments based on flags
        active_depts = []
        if has_woodwork:
            active_depts.append('woodwork')
        if has_metalwork:
            active_depts.append('metalwork')
        if has_finishing:
            active_depts.append('finishing')
        if has_upholstery:
            active_depts.append('upholstery')

        if not active_depts:
            active_depts = ['woodwork']  # Default

        # Split labor hours evenly across departments (simplified)
        hours_per_dept = estimated_labor_hours / len(active_depts)

        for dept in active_depts:
            labor_costs[f"labor_cost_{dept}"] = hours_per_dept * rates[dept]

        # Machine hours
        labor_costs["labor_cost_machine"] = estimated_machine_hours * rates["machine"]

        # Installation
        if installation_hours > 0:
            labor_costs["labor_cost_installation"] = (
                installation_hours *
                rates["installation"] *
                self.cost_tables["installation_multiplier"]
            )
        else:
            labor_costs["labor_cost_installation"] = 0

        return labor_costs

    def calculate_finishing_cost(
        self,
        surface_area_sqft: float,
        finishing_complexity: int,
        has_powder_coating: bool = False
    ) -> Dict[str, float]:
        """Calculate finishing and coating costs."""
        costs = {}

        # Standard finishing
        finishing_rate = self.cost_tables["finishing_costs_per_sqft"].get(
            finishing_complexity,
            self.cost_tables["finishing_costs_per_sqft"][3]
        )
        costs["finish_material_cost"] = surface_area_sqft * finishing_rate

        # Powder coating (additional)
        if has_powder_coating:
            costs["powder_coating_cost"] = (
                surface_area_sqft *
                self.cost_tables["powder_coating_per_sqft"]
            )
        else:
            costs["powder_coating_cost"] = 0

        return costs

    def calculate_delivery_cost(
        self,
        delivery_miles: float,
        is_heavy: bool = False
    ) -> float:
        """Calculate delivery cost based on distance."""
        delivery = self.cost_tables["delivery"]

        cost = delivery["base_fee"]
        cost += delivery_miles * delivery["per_mile"]

        if is_heavy:
            cost += delivery["heavy_item_surcharge"]

        return cost

    def calculate_overhead(self, direct_costs: float) -> float:
        """Calculate overhead allocation."""
        return direct_costs * self.cost_tables["overhead_pct"]

    def apply_complexity_adjustment(
        self,
        base_cost: float,
        job_complexity_score: int
    ) -> float:
        """Apply complexity multiplier to costs."""
        multiplier = self.cost_tables["complexity_multipliers"].get(
            job_complexity_score,
            self.cost_tables["complexity_multipliers"][3]
        )
        return base_cost * (multiplier - 1)  # Return just the adjustment

    def apply_risk_adjustment(
        self,
        base_cost: float,
        risk_adjustment_pct: float
    ) -> float:
        """Apply risk adjustment with cap."""
        max_adj = self.cost_tables["max_risk_adjustment_pct"]
        actual_adj = min(risk_adjustment_pct / 100, max_adj)
        return base_cost * actual_adj

    def calculate(
        self,
        # Dimensions
        length_in: float = 0,
        width_in: float = 0,
        height_in: float = 0,
        quantity: int = 1,

        # Materials
        wood_species: str = "Other",
        material_grade: str = "Standard",

        # Labor
        estimated_labor_hours: float = 0,
        estimated_machine_hours: float = 0,

        # Work types
        has_woodwork: bool = True,
        has_metalwork: bool = False,
        has_finishing: bool = True,
        has_upholstery: bool = False,
        has_powder_coating: bool = False,

        # Finishing
        finishing_complexity: int = 3,

        # Hardware
        hardware_cost: float = 0,

        # Logistics
        delivery_miles: float = 0,
        installation_required: bool = False,
        installation_hours: float = 0,

        # Adjustments
        job_complexity_score: int = 3,
        risk_adjustment_pct: float = 0,

        # Target margin
        target_margin_pct: float = 40.0,

        **kwargs  # Accept additional unused parameters
    ) -> CostBreakdown:
        """
        Calculate complete cost breakdown and suggested price.

        Args:
            All job parameters

        Returns:
            CostBreakdown with detailed costs and suggested price
        """
        breakdown = CostBreakdown()

        # Calculate surface area for finishing (in sq ft)
        surface_area_sqft = 2 * (
            (length_in * width_in) +
            (width_in * height_in) +
            (height_in * length_in)
        ) / 144  # Convert to sq ft

        # Material costs
        breakdown.material_cost = self.calculate_material_cost(
            wood_species=wood_species,
            material_grade=material_grade,
            length_in=length_in,
            width_in=width_in,
            height_in=height_in,
            quantity=quantity
        )

        # Hardware
        breakdown.hardware_cost = hardware_cost

        # Finishing costs
        finish_costs = self.calculate_finishing_cost(
            surface_area_sqft=surface_area_sqft * quantity,
            finishing_complexity=finishing_complexity,
            has_powder_coating=has_powder_coating
        )
        breakdown.finish_material_cost = finish_costs["finish_material_cost"]
        breakdown.powder_coating_cost = finish_costs["powder_coating_cost"]

        # Labor costs
        if installation_required and installation_hours == 0:
            # Estimate installation hours based on labor hours
            installation_hours = estimated_labor_hours * 0.25

        labor_costs = self.calculate_labor_cost(
            estimated_labor_hours=estimated_labor_hours,
            estimated_machine_hours=estimated_machine_hours,
            has_woodwork=has_woodwork,
            has_metalwork=has_metalwork,
            has_finishing=has_finishing,
            has_upholstery=has_upholstery,
            installation_hours=installation_hours if installation_required else 0
        )

        breakdown.labor_cost_woodwork = labor_costs.get("labor_cost_woodwork", 0)
        breakdown.labor_cost_metalwork = labor_costs.get("labor_cost_metalwork", 0)
        breakdown.labor_cost_finishing = labor_costs.get("labor_cost_finishing", 0)
        breakdown.labor_cost_upholstery = labor_costs.get("labor_cost_upholstery", 0)
        breakdown.labor_cost_machine = labor_costs.get("labor_cost_machine", 0)
        breakdown.labor_cost_installation = labor_costs.get("labor_cost_installation", 0)

        # Delivery
        is_heavy = (length_in * width_in * height_in * quantity) > 50000  # rough weight proxy
        breakdown.delivery_cost = self.calculate_delivery_cost(
            delivery_miles=delivery_miles,
            is_heavy=is_heavy
        ) if delivery_miles > 0 else 0

        # Calculate totals
        breakdown.total_material_cost = (
            breakdown.material_cost +
            breakdown.hardware_cost +
            breakdown.finish_material_cost +
            breakdown.powder_coating_cost
        )

        breakdown.total_labor_cost = sum([
            breakdown.labor_cost_woodwork,
            breakdown.labor_cost_metalwork,
            breakdown.labor_cost_finishing,
            breakdown.labor_cost_upholstery,
            breakdown.labor_cost_machine,
            breakdown.labor_cost_installation,
        ])

        breakdown.total_direct_cost = (
            breakdown.total_material_cost +
            breakdown.total_labor_cost +
            breakdown.delivery_cost
        )

        # Overhead
        breakdown.overhead_cost = self.calculate_overhead(breakdown.total_direct_cost)

        # Adjustments
        base_for_adjustments = breakdown.total_direct_cost + breakdown.overhead_cost

        breakdown.complexity_adjustment = self.apply_complexity_adjustment(
            base_for_adjustments,
            job_complexity_score
        )

        breakdown.risk_adjustment = self.apply_risk_adjustment(
            base_for_adjustments,
            risk_adjustment_pct
        )

        # Total cost
        breakdown.total_cost = (
            breakdown.total_direct_cost +
            breakdown.overhead_cost +
            breakdown.complexity_adjustment +
            breakdown.risk_adjustment
        )

        # Calculate suggested price with target margin
        # Price = Cost / (1 - margin%)
        if target_margin_pct < 100:
            breakdown.suggested_price = (
                breakdown.total_cost / (1 - target_margin_pct / 100)
            )
        else:
            breakdown.suggested_price = breakdown.total_cost * 2  # 50% margin fallback

        # Calculate actual margin
        if breakdown.suggested_price > 0:
            breakdown.gross_margin_pct = (
                (breakdown.suggested_price - breakdown.total_cost) /
                breakdown.suggested_price * 100
            )

        return breakdown

    def calculate_from_dict(self, params: Dict[str, Any]) -> CostBreakdown:
        """Calculate from a dictionary of parameters."""
        return self.calculate(**params)


def create_default_config(output_path: Path) -> None:
    """Create default configuration file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(DEFAULT_COST_TABLES, f, indent=2)
    print(f"Created default config at {output_path}")


if __name__ == '__main__':
    # Demo the should-cost model
    print("=" * 60)
    print("Should-Cost Model Demo")
    print("=" * 60)

    model = ShouldCostModel()

    # Save default config
    config_path = Path(__file__).parent.parent.parent / 'config' / 'cost_tables.json'
    create_default_config(config_path)

    # Example calculation
    breakdown = model.calculate(
        length_in=80,
        width_in=24,
        height_in=36,
        quantity=2,
        wood_species="Maple",
        material_grade="Premium",
        estimated_labor_hours=12,
        estimated_machine_hours=3,
        has_woodwork=True,
        has_finishing=True,
        finishing_complexity=4,
        hardware_cost=45,
        delivery_miles=15,
        installation_required=True,
        job_complexity_score=3,
        risk_adjustment_pct=5,
        target_margin_pct=45,
    )

    print("\nExample: Custom Maple Cabinet (2 units)")
    print("-" * 40)
    print(f"Material Cost: ${breakdown.material_cost:,.2f}")
    print(f"Hardware Cost: ${breakdown.hardware_cost:,.2f}")
    print(f"Finish Material: ${breakdown.finish_material_cost:,.2f}")
    print(f"Total Materials: ${breakdown.total_material_cost:,.2f}")
    print()
    print(f"Labor - Woodwork: ${breakdown.labor_cost_woodwork:,.2f}")
    print(f"Labor - Finishing: ${breakdown.labor_cost_finishing:,.2f}")
    print(f"Labor - Machine: ${breakdown.labor_cost_machine:,.2f}")
    print(f"Labor - Installation: ${breakdown.labor_cost_installation:,.2f}")
    print(f"Total Labor: ${breakdown.total_labor_cost:,.2f}")
    print()
    print(f"Delivery: ${breakdown.delivery_cost:,.2f}")
    print(f"Overhead: ${breakdown.overhead_cost:,.2f}")
    print(f"Complexity Adj: ${breakdown.complexity_adjustment:,.2f}")
    print(f"Risk Adj: ${breakdown.risk_adjustment:,.2f}")
    print()
    print(f"TOTAL COST: ${breakdown.total_cost:,.2f}")
    print(f"SUGGESTED PRICE: ${breakdown.suggested_price:,.2f}")
    print(f"Gross Margin: {breakdown.gross_margin_pct:.1f}%")
