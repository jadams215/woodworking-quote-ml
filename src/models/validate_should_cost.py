"""
Validate the should-cost model against actual quote data.

This script compares deterministic model outputs to historical quotes
to identify systematic biases and calibration needs.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import json

from .should_cost import ShouldCostModel, CostBreakdown


def load_validation_data(data_dir: Path) -> pd.DataFrame:
    """Load data for validation."""
    # Load combined processed data
    combined_path = data_dir / 'processed' / 'combined.csv'
    if combined_path.exists():
        return pd.read_csv(combined_path)

    # Fall back to raw data
    quotes_path = data_dir / 'combined_quotes.csv'
    if quotes_path.exists():
        return pd.read_csv(quotes_path)

    raise FileNotFoundError("No validation data found")


def safe_int(value, default=0):
    """Safely convert value to int, handling NaN."""
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    """Safely convert value to float, handling NaN."""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def prepare_model_input(row: pd.Series) -> Dict:
    """Convert a data row to model input parameters."""
    params = {
        'length_in': safe_float(row.get('length_in', 0)),
        'width_in': safe_float(row.get('width_in', 0)),
        'height_in': safe_float(row.get('height_in', 0)),
        'quantity': safe_int(row.get('quantity', 1), 1),
        'wood_species': row.get('wood_species', 'Other') if pd.notna(row.get('wood_species')) else 'Other',
        'material_grade': row.get('material_grade', 'Standard') if pd.notna(row.get('material_grade')) else 'Standard',
        'estimated_labor_hours': safe_float(row.get('estimated_labor_hours', 0)),
        'estimated_machine_hours': safe_float(row.get('estimated_machine_hours', 0)),
        'finishing_complexity': safe_int(row.get('finishing_complexity', 3), 3),
        'hardware_cost': safe_float(row.get('hardware_cost', 0)),
        'delivery_miles': safe_float(row.get('delivery_miles', 0)),
        'job_complexity_score': safe_int(row.get('job_complexity_score', 3), 3),
        'risk_adjustment_pct': safe_float(row.get('risk_adjustment_pct', 0)),
    }

    # Handle installation flag
    install = row.get('installation_required', 0)
    params['installation_required'] = str(install).lower() in ['yes', '1', 'true', '1.0']

    # Infer work types from data source
    params['has_woodwork'] = row.get('has_wood_work', 1) == 1
    params['has_metalwork'] = row.get('has_metal_work', 0) == 1
    params['has_finishing'] = row.get('has_finishing', 1) == 1
    params['has_powder_coating'] = row.get('has_powder_coating', 0) == 1
    params['has_upholstery'] = row.get('has_upholstery', 0) == 1

    return params


def validate_model(
    model: ShouldCostModel,
    df: pd.DataFrame,
    target_margin_pct: float = 40.0
) -> pd.DataFrame:
    """
    Run the model on all records and compare to actuals.

    Returns:
        DataFrame with predictions and error metrics
    """
    results = []

    for idx, row in df.iterrows():
        actual_price = row.get('quote_price', 0)

        if actual_price <= 0:
            continue

        try:
            params = prepare_model_input(row)
            params['target_margin_pct'] = target_margin_pct

            breakdown = model.calculate(**params)

            results.append({
                'index': idx,
                'data_source': row.get('data_source', 'unknown'),
                'project_name': row.get('project_name', row.get('project', 'Unknown')),
                'actual_price': actual_price,
                'predicted_price': breakdown.suggested_price,
                'should_cost': breakdown.total_cost,
                'material_cost': breakdown.total_material_cost,
                'labor_cost': breakdown.total_labor_cost,
                'overhead_cost': breakdown.overhead_cost,
                'error': breakdown.suggested_price - actual_price,
                'error_pct': (breakdown.suggested_price - actual_price) / actual_price * 100,
                'abs_error': abs(breakdown.suggested_price - actual_price),
                'abs_error_pct': abs(breakdown.suggested_price - actual_price) / actual_price * 100,
            })

        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            continue

    return pd.DataFrame(results)


def calculate_metrics(results_df: pd.DataFrame) -> Dict:
    """Calculate validation metrics."""
    if len(results_df) == 0:
        return {}

    metrics = {
        'n_samples': len(results_df),

        # Error metrics
        'mean_error': results_df['error'].mean(),
        'median_error': results_df['error'].median(),
        'mean_error_pct': results_df['error_pct'].mean(),
        'median_error_pct': results_df['error_pct'].median(),

        # Absolute error metrics
        'mae': results_df['abs_error'].mean(),
        'mae_pct': results_df['abs_error_pct'].mean(),
        'median_abs_error': results_df['abs_error'].median(),
        'median_abs_error_pct': results_df['abs_error_pct'].median(),

        # RMSE
        'rmse': np.sqrt((results_df['error'] ** 2).mean()),
        'rmse_pct': np.sqrt((results_df['error_pct'] ** 2).mean()),

        # Direction accuracy
        'within_10pct': (results_df['abs_error_pct'] <= 10).mean() * 100,
        'within_25pct': (results_df['abs_error_pct'] <= 25).mean() * 100,
        'within_50pct': (results_df['abs_error_pct'] <= 50).mean() * 100,

        # Bias (positive = overpricing, negative = underpricing)
        'overpriced_pct': (results_df['error'] > 0).mean() * 100,
        'underpriced_pct': (results_df['error'] < 0).mean() * 100,

        # Correlation
        'correlation': results_df['actual_price'].corr(results_df['predicted_price']),
    }

    return metrics


def print_validation_report(
    results_df: pd.DataFrame,
    metrics: Dict,
    by_source: bool = True
) -> None:
    """Print a detailed validation report."""
    print("\n" + "=" * 60)
    print("SHOULD-COST MODEL VALIDATION REPORT")
    print("=" * 60)

    print(f"\nSamples Validated: {metrics['n_samples']}")

    print("\n--- Error Metrics ---")
    print(f"Mean Error: ${metrics['mean_error']:,.2f} ({metrics['mean_error_pct']:.1f}%)")
    print(f"Median Error: ${metrics['median_error']:,.2f} ({metrics['median_error_pct']:.1f}%)")
    print(f"MAE: ${metrics['mae']:,.2f} ({metrics['mae_pct']:.1f}%)")
    print(f"RMSE: ${metrics['rmse']:,.2f} ({metrics['rmse_pct']:.1f}%)")

    print("\n--- Accuracy Bands ---")
    print(f"Within 10%: {metrics['within_10pct']:.1f}%")
    print(f"Within 25%: {metrics['within_25pct']:.1f}%")
    print(f"Within 50%: {metrics['within_50pct']:.1f}%")

    print("\n--- Bias Analysis ---")
    print(f"Overpriced: {metrics['overpriced_pct']:.1f}%")
    print(f"Underpriced: {metrics['underpriced_pct']:.1f}%")
    print(f"Correlation: {metrics['correlation']:.3f}")

    if by_source and 'data_source' in results_df.columns:
        print("\n--- By Data Source ---")
        for source in results_df['data_source'].unique():
            source_df = results_df[results_df['data_source'] == source]
            source_metrics = calculate_metrics(source_df)
            print(f"\n{source.upper()} ({len(source_df)} samples):")
            print(f"  MAE: ${source_metrics['mae']:,.2f} ({source_metrics['mae_pct']:.1f}%)")
            print(f"  Bias: {source_metrics['mean_error_pct']:.1f}%")

    # Show worst predictions
    print("\n--- Largest Errors ---")
    worst = results_df.nlargest(5, 'abs_error_pct')
    for _, row in worst.iterrows():
        project_name = str(row['project_name'])[:30] if pd.notna(row['project_name']) else 'Unknown'
        print(f"  {project_name}: "
              f"Actual ${row['actual_price']:,.0f}, "
              f"Predicted ${row['predicted_price']:,.0f} "
              f"({row['error_pct']:+.1f}%)")


def calibrate_model(
    model: ShouldCostModel,
    results_df: pd.DataFrame
) -> Dict[str, float]:
    """
    Suggest calibration adjustments based on validation results.

    Returns:
        Dictionary of suggested parameter adjustments
    """
    suggestions = {}

    # Check overall bias
    mean_error_pct = results_df['error_pct'].mean()

    if mean_error_pct > 20:
        suggestions['overhead_pct'] = model.cost_tables['overhead_pct'] * 0.8
        suggestions['note'] = "Model is overpricing - consider reducing overhead"
    elif mean_error_pct < -20:
        suggestions['overhead_pct'] = model.cost_tables['overhead_pct'] * 1.2
        suggestions['note'] = "Model is underpricing - consider increasing overhead"

    # Check by data source
    if 'data_source' in results_df.columns:
        for source in results_df['data_source'].unique():
            source_df = results_df[results_df['data_source'] == source]
            source_bias = source_df['error_pct'].mean()
            suggestions[f'{source}_bias_pct'] = source_bias

    return suggestions


def main():
    """Run validation pipeline."""
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data'

    print("=" * 60)
    print("Should-Cost Model Validation")
    print("=" * 60)

    # Load data
    print("\n--- Loading Data ---")
    try:
        df = load_validation_data(data_dir)
        print(f"Loaded {len(df)} records")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please run the data preparation pipeline first.")
        return

    # Filter to records with necessary features
    if 'quote_price' not in df.columns:
        print("Error: No quote_price column found")
        return

    # Initialize model
    config_path = project_root / 'config' / 'cost_tables.json'
    model = ShouldCostModel(config_path if config_path.exists() else None)

    # Run validation
    print("\n--- Running Validation ---")
    results_df = validate_model(model, df, target_margin_pct=40.0)

    if len(results_df) == 0:
        print("No valid records to validate")
        return

    # Calculate metrics
    metrics = calculate_metrics(results_df)

    # Print report
    print_validation_report(results_df, metrics)

    # Get calibration suggestions
    print("\n--- Calibration Suggestions ---")
    suggestions = calibrate_model(model, results_df)
    for key, value in suggestions.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    # Save results
    output_dir = data_dir / 'validation'
    output_dir.mkdir(exist_ok=True)

    results_df.to_csv(output_dir / 'should_cost_validation.csv', index=False)
    print(f"\nResults saved to {output_dir / 'should_cost_validation.csv'}")

    with open(output_dir / 'validation_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to {output_dir / 'validation_metrics.json'}")


if __name__ == '__main__':
    main()
