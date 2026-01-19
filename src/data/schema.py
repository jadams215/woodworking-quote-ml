"""
Unified data schema for woodworking quote prediction.

This module defines the standard schema for quote data and provides
utilities for data validation, cleaning, and transformation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import pandas as pd
import numpy as np


class WoodSpecies(str, Enum):
    """Supported wood species."""
    MAPLE = "Maple"
    OAK = "Oak"
    PINE = "Pine"
    MDF = "MDF"
    WALNUT = "Walnut"
    CHERRY = "Cherry"
    PLYWOOD = "Plywood"
    OTHER = "Other"


class MaterialGrade(str, Enum):
    """Material quality grades."""
    ECONOMY = "Economy"
    STANDARD = "Standard"
    PREMIUM = "Premium"


class FinishingComplexity(int, Enum):
    """Finishing complexity levels (1-5)."""
    MINIMAL = 1      # Raw or simple clear coat
    BASIC = 2        # Single color, simple finish
    MODERATE = 3     # Multiple colors or techniques
    COMPLEX = 4      # Custom finishes, multiple coats
    ELABORATE = 5    # Specialty finishes, hand detailing


class JobType(str, Enum):
    """Types of woodworking jobs."""
    MILLWORK = "Millwork"
    CABINETRY = "Cabinetry"
    FURNITURE = "Furniture"
    ARCHITECTURAL = "Architectural"
    UPHOLSTERY = "Upholstery"
    MIXED = "Mixed"


@dataclass
class QuoteInput:
    """
    Standard input schema for generating a woodworking quote.

    This represents the information needed to generate a quote.
    """
    # Project identification
    project_name: str
    customer_name: Optional[str] = None

    # Job characteristics
    job_type: JobType = JobType.MILLWORK
    job_description: Optional[str] = None

    # Dimensions (inches)
    length_in: float = 0.0
    width_in: float = 0.0
    height_in: float = 0.0

    # Materials
    wood_species: WoodSpecies = WoodSpecies.OTHER
    material_grade: MaterialGrade = MaterialGrade.STANDARD

    # Finishing
    finishing_complexity: FinishingComplexity = FinishingComplexity.MODERATE
    has_powder_coating: bool = False
    has_upholstery: bool = False

    # Quantity and labor
    quantity: int = 1
    estimated_labor_hours: float = 0.0
    estimated_machine_hours: float = 0.0

    # Logistics
    delivery_miles: float = 0.0
    installation_required: bool = False

    # Risk factors
    job_complexity_score: int = 3  # 1-5 scale
    risk_adjustment_pct: float = 0.0

    # Hardware/materials estimates
    hardware_cost: float = 0.0
    finish_material_cost: float = 0.0

    # Notes
    estimator_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ML model input."""
        return {
            'project_name': self.project_name,
            'customer_name': self.customer_name or '',
            'job_type': self.job_type.value if isinstance(self.job_type, JobType) else self.job_type,
            'length_in': self.length_in,
            'width_in': self.width_in,
            'height_in': self.height_in,
            'wood_species': self.wood_species.value if isinstance(self.wood_species, WoodSpecies) else self.wood_species,
            'material_grade': self.material_grade.value if isinstance(self.material_grade, MaterialGrade) else self.material_grade,
            'finishing_complexity': self.finishing_complexity.value if isinstance(self.finishing_complexity, FinishingComplexity) else self.finishing_complexity,
            'has_powder_coating': int(self.has_powder_coating),
            'has_upholstery': int(self.has_upholstery),
            'quantity': self.quantity,
            'estimated_labor_hours': self.estimated_labor_hours,
            'estimated_machine_hours': self.estimated_machine_hours,
            'delivery_miles': self.delivery_miles,
            'installation_required': int(self.installation_required),
            'job_complexity_score': self.job_complexity_score,
            'risk_adjustment_pct': self.risk_adjustment_pct,
            'hardware_cost': self.hardware_cost,
            'finish_material_cost': self.finish_material_cost,
        }


@dataclass
class QuoteOutput:
    """
    Standard output schema for a woodworking quote.

    Contains pricing tiers and detailed breakdowns.
    """
    # Core pricing
    should_cost: float  # Deterministic base cost
    ml_adjustment: float  # ML model adjustment
    final_price: float  # Combined estimate

    # Pricing tiers
    price_low: float  # Minimum viable price
    price_standard: float  # Recommended price
    price_premium: float  # Premium price

    # Cost breakdown
    material_cost: float = 0.0
    labor_cost: float = 0.0
    overhead_cost: float = 0.0
    delivery_cost: float = 0.0
    finishing_cost: float = 0.0
    hardware_cost: float = 0.0

    # Margins
    gross_margin_pct: float = 0.0
    net_margin_pct: float = 0.0

    # Confidence
    confidence_score: float = 0.0  # 0-100
    confidence_level: str = "Medium"  # Low/Medium/High
    requires_review: bool = False

    # Metadata
    notes: List[str] = field(default_factory=list)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize a dataframe for ML training.

    Args:
        df: Raw dataframe

    Returns:
        Cleaned dataframe
    """
    df = df.copy()

    # Handle missing values
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        df[col] = df[col].fillna(0)

    categorical_cols = df.select_dtypes(include=['object']).columns
    for col in categorical_cols:
        df[col] = df[col].fillna('Unknown')

    # Standardize categorical values
    if 'wood_species' in df.columns:
        df['wood_species'] = df['wood_species'].str.strip().str.title()

    if 'material_grade' in df.columns:
        df['material_grade'] = df['material_grade'].str.strip().str.title()

    if 'installation_required' in df.columns:
        # Convert Yes/No to 1/0
        df['installation_required'] = df['installation_required'].apply(
            lambda x: 1 if str(x).lower() in ['yes', '1', 'true'] else 0
        )

    # Remove outliers (prices outside 3 standard deviations)
    if 'quote_price' in df.columns:
        mean_price = df['quote_price'].mean()
        std_price = df['quote_price'].std()
        if std_price > 0:
            df = df[
                (df['quote_price'] >= mean_price - 3 * std_price) &
                (df['quote_price'] <= mean_price + 3 * std_price)
            ]

    return df


def validate_quote_input(data: Dict[str, Any]) -> List[str]:
    """
    Validate quote input data.

    Args:
        data: Dictionary of input values

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Required fields
    if not data.get('project_name'):
        errors.append("Project name is required")

    # Dimension validation
    for dim in ['length_in', 'width_in', 'height_in']:
        val = data.get(dim, 0)
        if val < 0:
            errors.append(f"{dim} cannot be negative")

    # Quantity validation
    qty = data.get('quantity', 1)
    if qty < 1:
        errors.append("Quantity must be at least 1")

    # Labor hours validation
    labor = data.get('estimated_labor_hours', 0)
    if labor < 0:
        errors.append("Labor hours cannot be negative")

    # Complexity score validation
    complexity = data.get('job_complexity_score', 3)
    if not 1 <= complexity <= 5:
        errors.append("Job complexity score must be between 1 and 5")

    return errors


def create_features_from_profitability(prof_df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform profitability data into ML-ready features.

    The profitability data contains actuals (what happened),
    but we need to derive features that would be known at quote time.
    """
    df = prof_df.copy()

    # Target: the quoted price (total income/sales)
    df['quote_price'] = df['total_income']

    # Derive job characteristics from cost structure
    df['has_metal_work'] = (df['metal_dept_supplies'] > 0).astype(int)
    df['has_wood_work'] = (df['wood_dept_supplies'] > 0).astype(int)
    df['has_finishing'] = (df['finish_dept_supplies'] > 0).astype(int)
    df['has_powder_coating'] = (df['powder_coating'] > 0).astype(int)
    df['has_upholstery'] = (df.get('upholstery_cost', 0) > 0).astype(int)

    # Complexity indicator based on number of departments involved
    df['num_departments'] = (
        df['has_metal_work'] +
        df['has_wood_work'] +
        df['has_finishing'] +
        df['has_powder_coating'] +
        df['has_upholstery']
    )

    # Cost ratios (useful for understanding job structure)
    df['labor_cost'] = df['hourly_costs']
    df['material_cost'] = df['total_cogs']

    df['labor_to_material_ratio'] = df.apply(
        lambda r: r['labor_cost'] / r['material_cost'] if r['material_cost'] > 0 else 1.0,
        axis=1
    )

    # Delivery cost
    df['delivery_cost'] = (
        df['freight_delivery'] +
        df['shipping_delivery'] +
        df['freight_delivery_cos']
    )

    # Overhead (other expenses)
    df['overhead_cost'] = df['total_expenses'] - df['hourly_costs'] - df['delivery_cost']
    df['overhead_cost'] = df['overhead_cost'].clip(lower=0)

    return df


def merge_quote_datasets(
    profitability_df: pd.DataFrame,
    quotes_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge profitability data with quote data for richer training set.

    The profitability data has cost breakdowns.
    The quotes data has detailed input features.

    We combine both to create a comprehensive training dataset.
    """
    # Process profitability data
    prof_features = create_features_from_profitability(profitability_df)

    # The datasets have different structures, so we'll concatenate
    # with appropriate column mapping

    # Create unified structure
    unified_records = []

    # Add profitability records
    for _, row in prof_features.iterrows():
        unified_records.append({
            'source': 'profitability',
            'project_name': row['project'],
            'quote_price': row['quote_price'],
            'material_cost': row['material_cost'],
            'labor_cost': row['labor_cost'],
            'delivery_cost': row['delivery_cost'],
            'overhead_cost': row['overhead_cost'],
            'has_metal_work': row['has_metal_work'],
            'has_wood_work': row['has_wood_work'],
            'has_finishing': row['has_finishing'],
            'has_powder_coating': row['has_powder_coating'],
            'has_upholstery': row['has_upholstery'],
            'num_departments': row['num_departments'],
            'gross_margin_pct': row['gross_margin_pct'],
            'net_margin_pct': row['net_margin_pct'],
        })

    # Add quote records
    for _, row in quotes_df.iterrows():
        record = {
            'source': 'quotes',
            'project_name': row.get('customer_name', 'Unknown'),
            'quote_price': row.get('quote_price', 0),
            'estimated_labor_hours': row.get('estimated_labor_hours', 0),
            'estimated_machine_hours': row.get('estimated_machine_hours', 0),
            'wood_species': row.get('wood_species', 'Unknown'),
            'material_grade': row.get('material_grade', 'Standard'),
            'finishing_complexity': row.get('finishing_complexity', 3),
            'length_in': row.get('length_in', 0),
            'width_in': row.get('width_in', 0),
            'height_in': row.get('height_in', 0),
            'quantity': row.get('quantity', 1),
            'delivery_miles': row.get('delivery_miles', 0),
            'installation_required': row.get('installation_required', 0),
            'hardware_cost': row.get('hardware_cost', 0),
            'finish_material_cost': row.get('finish_material_cost', 0),
            'job_complexity_score': row.get('job_complexity_score', 3),
            'risk_adjustment_pct': row.get('risk_adjustment_pct', 0),
        }
        unified_records.append(record)

    return pd.DataFrame(unified_records)
