"""
Quote Engine - Combines deterministic and ML models to generate pricing options.

This is the main interface for generating woodworking quotes. It:
1. Calculates base costs using the should-cost model
2. Applies ML adjustments based on historical patterns
3. Generates three pricing tiers (low, standard, premium)
4. Provides confidence scores and risk flags
5. Tracks lost quotes for future learning
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

from .should_cost import ShouldCostModel, CostBreakdown
from .ml_adjuster import MLCostAdjuster


@dataclass
class QuoteTier:
    """A single pricing tier."""
    name: str
    price: float
    margin_pct: float
    description: str
    features: List[str] = field(default_factory=list)
    recommended: bool = False


@dataclass
class QuoteResult:
    """Complete quote result with all tiers and metadata."""
    # Cost breakdown
    cost_breakdown: CostBreakdown

    # Pricing tiers
    tier_low: QuoteTier
    tier_standard: QuoteTier
    tier_premium: QuoteTier

    # ML adjustments
    ml_adjustment: float
    ml_adjustment_pct: float

    # Confidence metrics
    confidence_score: float  # 0-100
    confidence_level: str  # Low/Medium/High
    uncertainty_range: Tuple[float, float]  # Min/max price range

    # Risk flags
    requires_review: bool
    risk_flags: List[str] = field(default_factory=list)

    # Metadata
    quote_id: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'quote_id': self.quote_id,
            'generated_at': self.generated_at,
            'cost_breakdown': self.cost_breakdown.to_dict(),
            'tiers': {
                'low': {
                    'name': self.tier_low.name,
                    'price': self.tier_low.price,
                    'margin_pct': self.tier_low.margin_pct,
                    'description': self.tier_low.description,
                    'features': self.tier_low.features,
                    'recommended': self.tier_low.recommended,
                },
                'standard': {
                    'name': self.tier_standard.name,
                    'price': self.tier_standard.price,
                    'margin_pct': self.tier_standard.margin_pct,
                    'description': self.tier_standard.description,
                    'features': self.tier_standard.features,
                    'recommended': self.tier_standard.recommended,
                },
                'premium': {
                    'name': self.tier_premium.name,
                    'price': self.tier_premium.price,
                    'margin_pct': self.tier_premium.margin_pct,
                    'description': self.tier_premium.description,
                    'features': self.tier_premium.features,
                    'recommended': self.tier_premium.recommended,
                },
            },
            'ml_adjustment': self.ml_adjustment,
            'ml_adjustment_pct': self.ml_adjustment_pct,
            'confidence': {
                'score': self.confidence_score,
                'level': self.confidence_level,
                'range_low': self.uncertainty_range[0],
                'range_high': self.uncertainty_range[1],
            },
            'risk': {
                'requires_review': self.requires_review,
                'flags': self.risk_flags,
            },
            'notes': self.notes,
        }


@dataclass
class LostQuote:
    """Record of a quote that was lost to competition."""
    quote_id: str
    original_price: float
    winning_price: float
    price_difference: float
    difference_pct: float
    competitor: Optional[str]
    loss_reason: Optional[str]
    notes: str
    recorded_at: str

    # Original quote parameters (for retraining)
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletedProject:
    """
    Record of a completed project with actual vs quoted costs.

    Used to track accuracy and improve future quotes.
    """
    quote_id: str
    project_name: str

    # Original quote
    quoted_price: float
    quoted_cost: float
    quoted_margin_pct: float

    # Negotiated/final agreement
    final_agreed_price: float
    negotiation_rounds: int
    price_adjustments: List[Dict[str, Any]] = field(default_factory=list)

    # Actual costs after project completion
    actual_material_cost: float = 0.0
    actual_labor_cost: float = 0.0
    actual_overhead_cost: float = 0.0
    actual_delivery_cost: float = 0.0
    actual_total_cost: float = 0.0

    # Variance analysis
    cost_variance: float = 0.0  # actual - quoted
    cost_variance_pct: float = 0.0
    margin_achieved: float = 0.0
    margin_achieved_pct: float = 0.0

    # Project details
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    customer_satisfaction: Optional[int] = None  # 1-5 rating
    issues_encountered: List[str] = field(default_factory=list)
    lessons_learned: str = ""

    # Metadata
    recorded_at: str = ""
    original_parameters: Dict[str, Any] = field(default_factory=dict)

    def calculate_variances(self) -> None:
        """Calculate variance metrics."""
        if self.quoted_cost > 0:
            self.cost_variance = self.actual_total_cost - self.quoted_cost
            self.cost_variance_pct = (self.cost_variance / self.quoted_cost) * 100

        if self.final_agreed_price > 0:
            self.margin_achieved = self.final_agreed_price - self.actual_total_cost
            self.margin_achieved_pct = (self.margin_achieved / self.final_agreed_price) * 100


class QuoteEngine:
    """
    Main quote generation engine.

    Combines should-cost model, ML adjustments, and pricing rules
    to generate comprehensive quotes with confidence scores.
    """

    # Default margin targets for each tier
    DEFAULT_MARGINS = {
        'low': 25.0,      # Minimum viable margin
        'standard': 40.0,  # Target margin
        'premium': 55.0,   # Premium margin
    }

    # Confidence thresholds
    CONFIDENCE_THRESHOLDS = {
        'high': 75,
        'medium': 50,
    }

    def __init__(
        self,
        config_path: Optional[Path] = None,
        model_dir: Optional[Path] = None,
        margin_targets: Optional[Dict[str, float]] = None
    ):
        """
        Initialize the quote engine.

        Args:
            config_path: Path to cost tables config
            model_dir: Path to trained ML model
            margin_targets: Custom margin targets for tiers
        """
        # Initialize should-cost model
        self.should_cost_model = ShouldCostModel(config_path)

        # Initialize ML adjuster
        self.ml_adjuster: Optional[MLCostAdjuster] = None
        if model_dir and (model_dir / 'ml_adjuster').exists():
            self.ml_adjuster = MLCostAdjuster()
            self.ml_adjuster.load(model_dir / 'ml_adjuster')

        # Margin targets
        self.margin_targets = margin_targets or self.DEFAULT_MARGINS.copy()

        # Lost quote tracking
        self.lost_quotes: List[LostQuote] = []
        self.lost_quotes_path: Optional[Path] = None

        # Completed project tracking
        self.completed_projects: List[CompletedProject] = []
        self.completed_projects_path: Optional[Path] = None

    def set_lost_quotes_path(self, path: Path) -> None:
        """Set path for persistent lost quote storage."""
        self.lost_quotes_path = path
        if path.exists():
            self._load_lost_quotes()

    def _load_lost_quotes(self) -> None:
        """Load lost quotes from file."""
        if self.lost_quotes_path and self.lost_quotes_path.exists():
            with open(self.lost_quotes_path, 'r') as f:
                data = json.load(f)
            self.lost_quotes = [LostQuote(**q) for q in data]

    def _save_lost_quotes(self) -> None:
        """Save lost quotes to file."""
        if self.lost_quotes_path:
            self.lost_quotes_path.parent.mkdir(parents=True, exist_ok=True)
            data = [
                {
                    'quote_id': q.quote_id,
                    'original_price': q.original_price,
                    'winning_price': q.winning_price,
                    'price_difference': q.price_difference,
                    'difference_pct': q.difference_pct,
                    'competitor': q.competitor,
                    'loss_reason': q.loss_reason,
                    'notes': q.notes,
                    'recorded_at': q.recorded_at,
                    'parameters': q.parameters,
                }
                for q in self.lost_quotes
            ]
            with open(self.lost_quotes_path, 'w') as f:
                json.dump(data, f, indent=2)

    def record_lost_quote(
        self,
        quote_id: str,
        original_price: float,
        winning_price: float,
        parameters: Dict[str, Any],
        competitor: Optional[str] = None,
        loss_reason: Optional[str] = None,
        notes: str = ""
    ) -> LostQuote:
        """
        Record a lost quote for future analysis and model improvement.

        Args:
            quote_id: ID of the original quote
            original_price: Our quoted price
            winning_price: Price that won the job
            parameters: Original quote parameters
            competitor: Name of winning competitor (if known)
            loss_reason: Reason for loss (price, quality, timing, etc.)
            notes: Additional notes

        Returns:
            The recorded LostQuote object
        """
        lost_quote = LostQuote(
            quote_id=quote_id,
            original_price=original_price,
            winning_price=winning_price,
            price_difference=original_price - winning_price,
            difference_pct=((original_price - winning_price) / winning_price) * 100,
            competitor=competitor,
            loss_reason=loss_reason,
            notes=notes,
            recorded_at=datetime.now().isoformat(),
            parameters=parameters,
        )

        self.lost_quotes.append(lost_quote)
        self._save_lost_quotes()

        return lost_quote

    def get_lost_quote_insights(self) -> Dict[str, Any]:
        """
        Analyze lost quotes to provide pricing insights.

        Returns:
            Dictionary with insights and recommendations
        """
        if not self.lost_quotes:
            return {'message': 'No lost quotes recorded yet'}

        differences = [q.difference_pct for q in self.lost_quotes]

        insights = {
            'total_lost_quotes': len(self.lost_quotes),
            'avg_overpriced_pct': np.mean(differences),
            'median_overpriced_pct': np.median(differences),
            'max_overpriced_pct': max(differences),
            'min_overpriced_pct': min(differences),

            # Recommendations
            'suggested_margin_reduction': max(0, np.median(differences) * 0.5),

            # By reason
            'by_reason': {},
            'by_competitor': {},
        }

        # Group by reason
        for q in self.lost_quotes:
            reason = q.loss_reason or 'Unknown'
            if reason not in insights['by_reason']:
                insights['by_reason'][reason] = []
            insights['by_reason'][reason].append(q.difference_pct)

        # Group by competitor
        for q in self.lost_quotes:
            competitor = q.competitor or 'Unknown'
            if competitor not in insights['by_competitor']:
                insights['by_competitor'][competitor] = []
            insights['by_competitor'][competitor].append(q.difference_pct)

        return insights

    def set_completed_projects_path(self, path: Path) -> None:
        """Set path for persistent completed project storage."""
        self.completed_projects_path = path
        if path.exists():
            self._load_completed_projects()

    def _load_completed_projects(self) -> None:
        """Load completed projects from file."""
        if self.completed_projects_path and self.completed_projects_path.exists():
            with open(self.completed_projects_path, 'r') as f:
                data = json.load(f)
            self.completed_projects = [CompletedProject(**p) for p in data]

    def _save_completed_projects(self) -> None:
        """Save completed projects to file."""
        if self.completed_projects_path:
            self.completed_projects_path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for p in self.completed_projects:
                data.append({
                    'quote_id': p.quote_id,
                    'project_name': p.project_name,
                    'quoted_price': p.quoted_price,
                    'quoted_cost': p.quoted_cost,
                    'quoted_margin_pct': p.quoted_margin_pct,
                    'final_agreed_price': p.final_agreed_price,
                    'negotiation_rounds': p.negotiation_rounds,
                    'price_adjustments': p.price_adjustments,
                    'actual_material_cost': p.actual_material_cost,
                    'actual_labor_cost': p.actual_labor_cost,
                    'actual_overhead_cost': p.actual_overhead_cost,
                    'actual_delivery_cost': p.actual_delivery_cost,
                    'actual_total_cost': p.actual_total_cost,
                    'cost_variance': p.cost_variance,
                    'cost_variance_pct': p.cost_variance_pct,
                    'margin_achieved': p.margin_achieved,
                    'margin_achieved_pct': p.margin_achieved_pct,
                    'start_date': p.start_date,
                    'end_date': p.end_date,
                    'customer_satisfaction': p.customer_satisfaction,
                    'issues_encountered': p.issues_encountered,
                    'lessons_learned': p.lessons_learned,
                    'recorded_at': p.recorded_at,
                    'original_parameters': p.original_parameters,
                })
            with open(self.completed_projects_path, 'w') as f:
                json.dump(data, f, indent=2)

    def record_negotiation(
        self,
        quote_id: str,
        adjustment_type: str,
        old_price: float,
        new_price: float,
        reason: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Record a price adjustment during customer negotiation.

        Args:
            quote_id: Quote ID being adjusted
            adjustment_type: Type of adjustment (discount, scope_change, material_change, etc.)
            old_price: Previous price
            new_price: New adjusted price
            reason: Reason for adjustment
            notes: Additional notes

        Returns:
            The adjustment record
        """
        adjustment = {
            'timestamp': datetime.now().isoformat(),
            'adjustment_type': adjustment_type,
            'old_price': old_price,
            'new_price': new_price,
            'difference': new_price - old_price,
            'difference_pct': ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0,
            'reason': reason,
            'notes': notes,
        }
        return adjustment

    def complete_project(
        self,
        quote_id: str,
        project_name: str,
        quoted_price: float,
        quoted_cost: float,
        final_agreed_price: float,
        negotiation_rounds: int,
        price_adjustments: List[Dict[str, Any]],
        actual_costs: Dict[str, float],
        parameters: Dict[str, Any],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        customer_satisfaction: Optional[int] = None,
        issues: Optional[List[str]] = None,
        lessons_learned: str = ""
    ) -> CompletedProject:
        """
        Record a completed project with actual costs.

        Args:
            quote_id: Original quote ID
            project_name: Project name
            quoted_price: Original quoted price
            quoted_cost: Original quoted cost
            final_agreed_price: Final agreed price after negotiations
            negotiation_rounds: Number of negotiation rounds
            price_adjustments: List of price adjustments during negotiation
            actual_costs: Dict with material_cost, labor_cost, overhead_cost, delivery_cost
            parameters: Original quote parameters
            start_date: Project start date
            end_date: Project end date
            customer_satisfaction: Customer satisfaction rating (1-5)
            issues: List of issues encountered
            lessons_learned: Lessons learned text

        Returns:
            CompletedProject record
        """
        project = CompletedProject(
            quote_id=quote_id,
            project_name=project_name,
            quoted_price=quoted_price,
            quoted_cost=quoted_cost,
            quoted_margin_pct=((quoted_price - quoted_cost) / quoted_price) * 100 if quoted_price > 0 else 0,
            final_agreed_price=final_agreed_price,
            negotiation_rounds=negotiation_rounds,
            price_adjustments=price_adjustments,
            actual_material_cost=actual_costs.get('material_cost', 0),
            actual_labor_cost=actual_costs.get('labor_cost', 0),
            actual_overhead_cost=actual_costs.get('overhead_cost', 0),
            actual_delivery_cost=actual_costs.get('delivery_cost', 0),
            actual_total_cost=sum(actual_costs.values()),
            start_date=start_date,
            end_date=end_date,
            customer_satisfaction=customer_satisfaction,
            issues_encountered=issues or [],
            lessons_learned=lessons_learned,
            recorded_at=datetime.now().isoformat(),
            original_parameters=parameters,
        )

        project.calculate_variances()
        self.completed_projects.append(project)
        self._save_completed_projects()

        return project

    def get_project_insights(self) -> Dict[str, Any]:
        """
        Analyze completed projects to provide estimating insights.

        Returns:
            Dictionary with insights and recommendations
        """
        if not self.completed_projects:
            return {'message': 'No completed projects recorded yet'}

        cost_variances = [p.cost_variance_pct for p in self.completed_projects]
        margin_achieved = [p.margin_achieved_pct for p in self.completed_projects]

        insights = {
            'total_projects': len(self.completed_projects),

            # Cost accuracy
            'avg_cost_variance_pct': np.mean(cost_variances),
            'median_cost_variance_pct': np.median(cost_variances),
            'cost_underestimate_pct': sum(1 for v in cost_variances if v > 0) / len(cost_variances) * 100,
            'cost_overestimate_pct': sum(1 for v in cost_variances if v < 0) / len(cost_variances) * 100,

            # Margin performance
            'avg_margin_achieved_pct': np.mean(margin_achieved),
            'median_margin_achieved_pct': np.median(margin_achieved),

            # Negotiation patterns
            'avg_negotiation_rounds': np.mean([p.negotiation_rounds for p in self.completed_projects]),
            'avg_discount_from_original': np.mean([
                ((p.quoted_price - p.final_agreed_price) / p.quoted_price) * 100
                for p in self.completed_projects if p.quoted_price > 0
            ]),

            # Customer satisfaction
            'avg_satisfaction': np.mean([
                p.customer_satisfaction for p in self.completed_projects
                if p.customer_satisfaction is not None
            ]) if any(p.customer_satisfaction for p in self.completed_projects) else None,

            # Cost component variances
            'material_cost_variance': [],
            'labor_cost_variance': [],
        }

        # Recommendations based on patterns
        if insights['avg_cost_variance_pct'] > 10:
            insights['recommendation'] = "Costs consistently underestimated - consider adding a buffer to estimates"
        elif insights['avg_cost_variance_pct'] < -10:
            insights['recommendation'] = "Costs consistently overestimated - estimates may be too conservative"
        else:
            insights['recommendation'] = "Cost estimates are reasonably accurate"

        return insights

    def calculate_confidence(
        self,
        params: Dict[str, Any],
        ml_uncertainty: float = 0
    ) -> Tuple[float, str, List[str]]:
        """
        Calculate confidence score and identify risk flags.

        Args:
            params: Quote parameters
            ml_uncertainty: Uncertainty from ML model

        Returns:
            Tuple of (confidence_score, confidence_level, risk_flags)
        """
        confidence = 100.0
        risk_flags = []

        # Penalize missing key parameters
        key_params = ['estimated_labor_hours', 'length_in', 'width_in', 'height_in']
        missing_count = sum(1 for p in key_params if params.get(p, 0) == 0)
        if missing_count > 0:
            confidence -= missing_count * 10
            risk_flags.append(f"Missing {missing_count} key parameters")

        # Penalize high complexity
        complexity = params.get('job_complexity_score', 3)
        if complexity >= 4:
            confidence -= 10
            risk_flags.append("High complexity job")

        # Penalize high risk adjustment
        risk_pct = params.get('risk_adjustment_pct', 0)
        if risk_pct >= 10:
            confidence -= 15
            risk_flags.append(f"High risk adjustment ({risk_pct}%)")

        # Factor in ML uncertainty
        if ml_uncertainty > 0:
            # Normalize uncertainty relative to typical quote prices
            normalized_uncertainty = min(ml_uncertainty / 10000, 30)
            confidence -= normalized_uncertainty

        # Penalize unusual dimensions
        volume = (
            params.get('length_in', 0) *
            params.get('width_in', 0) *
            params.get('height_in', 0)
        )
        if volume > 500000:  # Large item
            confidence -= 5
            risk_flags.append("Large dimensions - verify manually")

        # Check against lost quote patterns
        if self.lost_quotes:
            insights = self.get_lost_quote_insights()
            if insights['avg_overpriced_pct'] > 20:
                confidence -= 10
                risk_flags.append(f"Historical quotes avg {insights['avg_overpriced_pct']:.0f}% above market")

        # Clamp confidence
        confidence = max(0, min(100, confidence))

        # Determine level
        if confidence >= self.CONFIDENCE_THRESHOLDS['high']:
            level = 'High'
        elif confidence >= self.CONFIDENCE_THRESHOLDS['medium']:
            level = 'Medium'
        else:
            level = 'Low'

        return confidence, level, risk_flags

    def generate_quote(
        self,
        params: Dict[str, Any],
        include_ml: bool = True
    ) -> QuoteResult:
        """
        Generate a complete quote with all tiers.

        Args:
            params: Quote parameters
            include_ml: Whether to apply ML adjustments

        Returns:
            QuoteResult with all pricing tiers and metadata
        """
        # Generate unique quote ID
        quote_id = f"Q-{datetime.now().strftime('%Y%m%d%H%M%S')}-{np.random.randint(1000, 9999)}"

        # Calculate should-cost
        cost_breakdown = self.should_cost_model.calculate(**params)
        base_cost = cost_breakdown.total_cost

        # Apply ML adjustment
        ml_adjustment = 0.0
        ml_uncertainty = 0.0

        if include_ml and self.ml_adjuster is not None:
            try:
                # Create DataFrame for prediction
                df = pd.DataFrame([params])
                predictions, uncertainties = self.ml_adjuster.predict_with_uncertainty(df)

                # The ML model predicts the final price, so adjustment is prediction - should_cost
                ml_predicted_price = predictions[0]
                ml_adjustment = ml_predicted_price - cost_breakdown.suggested_price
                ml_uncertainty = uncertainties[0] if len(uncertainties) > 0 else 0

            except Exception as e:
                print(f"ML adjustment failed: {e}")

        ml_adjustment_pct = (ml_adjustment / base_cost * 100) if base_cost > 0 else 0

        # Calculate confidence
        confidence_score, confidence_level, risk_flags = self.calculate_confidence(
            params, ml_uncertainty
        )

        # Adjust margins based on lost quote insights
        adjusted_margins = self.margin_targets.copy()
        if self.lost_quotes:
            insights = self.get_lost_quote_insights()
            margin_reduction = insights.get('suggested_margin_reduction', 0)
            if margin_reduction > 0:
                adjusted_margins['low'] = max(15, adjusted_margins['low'] - margin_reduction)
                adjusted_margins['standard'] = max(25, adjusted_margins['standard'] - margin_reduction * 0.5)

        # Generate tier prices
        def price_for_margin(cost: float, margin_pct: float) -> float:
            return cost / (1 - margin_pct / 100)

        base_for_tiers = base_cost + ml_adjustment * 0.5  # Partial ML adjustment

        price_low = price_for_margin(base_for_tiers, adjusted_margins['low'])
        price_standard = price_for_margin(base_for_tiers, adjusted_margins['standard'])
        price_premium = price_for_margin(base_for_tiers, adjusted_margins['premium'])

        # Create tier descriptions
        tier_low = QuoteTier(
            name="Value",
            price=round(price_low, 2),
            margin_pct=adjusted_margins['low'],
            description="Competitive pricing with standard service",
            features=[
                "Standard materials",
                "Standard delivery",
                "30-day warranty",
            ],
            recommended=False,
        )

        tier_standard = QuoteTier(
            name="Standard",
            price=round(price_standard, 2),
            margin_pct=adjusted_margins['standard'],
            description="Recommended option with full service",
            features=[
                "Premium materials",
                "Expedited delivery available",
                "90-day warranty",
                "Dedicated project manager",
            ],
            recommended=True,
        )

        tier_premium = QuoteTier(
            name="Premium",
            price=round(price_premium, 2),
            margin_pct=adjusted_margins['premium'],
            description="White-glove service with priority handling",
            features=[
                "Premium materials",
                "Priority scheduling",
                "Expedited delivery included",
                "1-year warranty",
                "Dedicated project manager",
                "Site visit included",
            ],
            recommended=False,
        )

        # Calculate uncertainty range
        uncertainty_pct = max(10, 100 - confidence_score)  # Higher uncertainty for lower confidence
        uncertainty_range = (
            round(price_standard * (1 - uncertainty_pct / 200), 2),
            round(price_standard * (1 + uncertainty_pct / 200), 2),
        )

        # Build notes
        notes = []
        if ml_adjustment != 0:
            direction = "up" if ml_adjustment > 0 else "down"
            notes.append(f"ML adjustment: ${abs(ml_adjustment):,.2f} {direction} ({ml_adjustment_pct:+.1f}%)")

        if confidence_level == 'Low':
            notes.append("Low confidence - manual review recommended")

        return QuoteResult(
            cost_breakdown=cost_breakdown,
            tier_low=tier_low,
            tier_standard=tier_standard,
            tier_premium=tier_premium,
            ml_adjustment=ml_adjustment,
            ml_adjustment_pct=ml_adjustment_pct,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            uncertainty_range=uncertainty_range,
            requires_review=confidence_level == 'Low' or len(risk_flags) > 2,
            risk_flags=risk_flags,
            quote_id=quote_id,
            generated_at=datetime.now().isoformat(),
            notes=notes,
        )


def demo_quote_engine():
    """Demonstrate the quote engine."""
    print("=" * 60)
    print("Quote Engine Demo")
    print("=" * 60)

    # Initialize engine
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / 'config' / 'cost_tables.json'
    model_dir = project_root / 'models'

    engine = QuoteEngine(
        config_path=config_path if config_path.exists() else None,
        model_dir=model_dir if model_dir.exists() else None,
    )

    # Set up lost quote tracking
    engine.set_lost_quotes_path(project_root / 'data' / 'lost_quotes.json')

    # Example quote request
    params = {
        'length_in': 80,
        'width_in': 24,
        'height_in': 36,
        'quantity': 2,
        'wood_species': 'Maple',
        'material_grade': 'Premium',
        'estimated_labor_hours': 12,
        'estimated_machine_hours': 3,
        'has_woodwork': True,
        'has_finishing': True,
        'finishing_complexity': 4,
        'hardware_cost': 45,
        'delivery_miles': 15,
        'installation_required': True,
        'job_complexity_score': 3,
        'risk_adjustment_pct': 5,
    }

    print("\nGenerating quote for: Custom Maple Cabinet (2 units)")
    print("-" * 40)

    result = engine.generate_quote(params)

    print(f"\nQuote ID: {result.quote_id}")
    print(f"Generated: {result.generated_at}")

    print(f"\n--- Cost Breakdown ---")
    print(f"Materials: ${result.cost_breakdown.total_material_cost:,.2f}")
    print(f"Labor: ${result.cost_breakdown.total_labor_cost:,.2f}")
    print(f"Overhead: ${result.cost_breakdown.overhead_cost:,.2f}")
    print(f"Total Cost: ${result.cost_breakdown.total_cost:,.2f}")

    print(f"\n--- Pricing Tiers ---")
    for tier in [result.tier_low, result.tier_standard, result.tier_premium]:
        rec = " (RECOMMENDED)" if tier.recommended else ""
        print(f"\n{tier.name}{rec}: ${tier.price:,.2f}")
        print(f"  Margin: {tier.margin_pct:.0f}%")
        print(f"  {tier.description}")

    print(f"\n--- Confidence ---")
    print(f"Score: {result.confidence_score:.0f}/100 ({result.confidence_level})")
    print(f"Price Range: ${result.uncertainty_range[0]:,.2f} - ${result.uncertainty_range[1]:,.2f}")

    if result.risk_flags:
        print(f"\n--- Risk Flags ---")
        for flag in result.risk_flags:
            print(f"  ! {flag}")

    if result.notes:
        print(f"\n--- Notes ---")
        for note in result.notes:
            print(f"  - {note}")

    # Demonstrate lost quote recording
    print("\n" + "=" * 60)
    print("Recording a sample lost quote...")
    print("=" * 60)

    lost = engine.record_lost_quote(
        quote_id=result.quote_id,
        original_price=result.tier_standard.price,
        winning_price=result.tier_standard.price * 0.85,  # Lost by 15%
        parameters=params,
        competitor="ABC Woodworks",
        loss_reason="Price",
        notes="Customer went with lower bid despite quality concerns"
    )

    print(f"\nLost quote recorded:")
    print(f"  Our price: ${lost.original_price:,.2f}")
    print(f"  Winning price: ${lost.winning_price:,.2f}")
    print(f"  Difference: {lost.difference_pct:+.1f}%")

    # Show insights
    insights = engine.get_lost_quote_insights()
    print(f"\nLost Quote Insights:")
    print(f"  Total lost: {insights['total_lost_quotes']}")
    print(f"  Avg overpriced: {insights['avg_overpriced_pct']:.1f}%")
    print(f"  Suggested margin reduction: {insights['suggested_margin_reduction']:.1f}%")


if __name__ == '__main__':
    demo_quote_engine()
