"""
Ingest B10 Union LLC Project Profitability files into structured dataset.

This module parses the profitability reports (text format with tab-separated values)
and extracts cost components that can be used for training the quote prediction model.
"""

import pandas as pd
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def parse_currency(value) -> float:
    """Convert currency string to float."""
    if pd.isna(value) or value == '' or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    # Remove currency symbols, commas, spaces, quotes, and handle parentheses for negatives
    cleaned = str(value).replace('$', '').replace(',', '').replace('"', '').strip()
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = '-' + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_project_name_from_content(content: str) -> str:
    """Extract project name from file content."""
    lines = content.split('\n')
    for line in lines:
        if 'Project Profitability for' in line:
            # Extract the project name after "for"
            match = re.search(r"Project Profitability for (.+?)[\t\n]", line)
            if match:
                return match.group(1).strip()
    return "Unknown Project"


def parse_profitability_text(filepath: str) -> Optional[Dict]:
    """
    Parse a single B10 Union profitability text file (tab-separated format).

    Returns a dictionary with extracted cost components.
    """
    try:
        # Read the text file
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Initialize result dictionary
        result = {
            'source_file': os.path.basename(filepath),
            'project': extract_project_name_from_content(content),

            # Income
            'sales_revenue': 0.0,
            'upholstery_revenue': 0.0,
            'total_income': 0.0,

            # Cost of Goods Sold - Materials
            'cogs_direct': 0.0,
            'powder_coating': 0.0,
            'finish_dept_supplies': 0.0,
            'freight_delivery_cos': 0.0,
            'metal_dept_supplies': 0.0,
            'wood_dept_supplies': 0.0,
            'upholstery_cost': 0.0,
            'job_materials': 0.0,
            'supplies_materials_cogs': 0.0,
            'total_cogs': 0.0,

            # Gross Profit
            'gross_profit': 0.0,

            # Expenses
            'hourly_costs': 0.0,  # Labor
            'freight_delivery': 0.0,
            'shipping_delivery': 0.0,
            'car_truck_fuel': 0.0,
            'event_expenses': 0.0,
            'total_expenses': 0.0,

            # Net Income
            'net_operating_income': 0.0,
            'net_income': 0.0,
        }

        # Parse line by line - format is "Label\tValue"
        lines = content.split('\n')

        # Track the last "Total Cost of Goods Sold" (there can be multiple subtotals)
        last_total_cogs = 0.0

        for line in lines:
            # Split by tab
            parts = line.split('\t')
            if len(parts) < 2:
                continue

            label = parts[0].strip()
            value_str = parts[1].strip() if len(parts) > 1 else ''

            label_lower = label.lower().strip()

            # Skip empty values
            if not value_str:
                continue

            value = parse_currency(value_str)

            # Extract values based on label matching
            if label_lower == 'sales':
                result['sales_revenue'] = value
            elif label_lower == 'upholstery' and 'income' not in label_lower:
                # Could be revenue or cost depending on context
                # In Income section it's revenue, in COGS it's cost
                # We'll handle this by position - check if we've seen Total Income yet
                if result['total_income'] == 0:
                    result['upholstery_revenue'] = value
                else:
                    result['upholstery_cost'] = value
            elif label_lower == 'total sales':
                # If there's a total sales, use it as sales_revenue
                result['sales_revenue'] = value
            elif label_lower == 'total income':
                result['total_income'] = value
            elif label_lower == 'cost of goods sold' and not label_lower.startswith('total'):
                result['cogs_direct'] = value
            elif 'powder coating' in label_lower:
                result['powder_coating'] = value
            elif 'finish dept' in label_lower:
                result['finish_dept_supplies'] = value
            elif 'freight' in label_lower and 'cos' in label_lower:
                result['freight_delivery_cos'] = value
            elif 'metal dept' in label_lower:
                result['metal_dept_supplies'] = value
            elif 'wood dept' in label_lower:
                result['wood_dept_supplies'] = value
            elif label_lower == 'upholstery':
                result['upholstery_cost'] = value
            elif 'job materials' in label_lower:
                result['job_materials'] = value
            elif 'total supplies & materials' in label_lower:
                result['supplies_materials_cogs'] = value
            elif label_lower == 'total cost of goods sold':
                last_total_cogs = value
            elif label_lower == 'gross profit':
                result['gross_profit'] = value
            elif 'hourly costs' in label_lower:
                result['hourly_costs'] = value
            elif label_lower == 'freight & delivery':
                result['freight_delivery'] = value
            elif 'shipping' in label_lower and 'delivery' in label_lower:
                result['shipping_delivery'] = value
            elif label_lower == 'fuel':
                result['car_truck_fuel'] = value
            elif 'event' in label_lower:
                result['event_expenses'] = value
            elif label_lower == 'total expenses':
                result['total_expenses'] = value
            elif label_lower == 'net operating income':
                result['net_operating_income'] = value
            elif label_lower == 'net income':
                result['net_income'] = value

        # Use the final total_cogs value
        result['total_cogs'] = last_total_cogs

        # Compute derived metrics
        if result['total_income'] > 0:
            result['gross_margin_pct'] = (result['gross_profit'] / result['total_income']) * 100
            result['net_margin_pct'] = (result['net_income'] / result['total_income']) * 100
            result['labor_pct_of_revenue'] = (result['hourly_costs'] / result['total_income']) * 100
            result['materials_pct_of_revenue'] = (result['total_cogs'] / result['total_income']) * 100
        else:
            result['gross_margin_pct'] = 0.0
            result['net_margin_pct'] = 0.0
            result['labor_pct_of_revenue'] = 0.0
            result['materials_pct_of_revenue'] = 0.0

        return result

    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None


def ingest_all_profitability_files(data_dir: str) -> pd.DataFrame:
    """
    Ingest all profitability text files from a directory.

    Args:
        data_dir: Directory containing the text files

    Returns:
        DataFrame with all parsed profitability data
    """
    records = []
    seen_projects = set()  # Track unique projects to avoid duplicates

    # Find all text files matching the pattern
    for filename in os.listdir(data_dir):
        if filename.endswith('.txt') and 'Profitability' in filename:
            filepath = os.path.join(data_dir, filename)
            print(f"Parsing: {filename}")

            record = parse_profitability_text(filepath)
            if record:
                # Check for duplicates based on project name and income
                project_key = (record['project'], record['total_income'])
                if project_key not in seen_projects:
                    seen_projects.add(project_key)
                    records.append(record)
                else:
                    print(f"  Skipping duplicate: {record['project']}")

    if not records:
        print("No profitability files found or parsed successfully.")
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Reorder columns for clarity
    column_order = [
        'source_file', 'project',
        'sales_revenue', 'upholstery_revenue', 'total_income',
        'cogs_direct', 'powder_coating', 'finish_dept_supplies',
        'freight_delivery_cos', 'metal_dept_supplies', 'wood_dept_supplies',
        'upholstery_cost', 'job_materials', 'supplies_materials_cogs', 'total_cogs',
        'gross_profit', 'gross_margin_pct',
        'hourly_costs', 'freight_delivery', 'shipping_delivery',
        'car_truck_fuel', 'event_expenses', 'total_expenses',
        'net_operating_income', 'net_income', 'net_margin_pct',
        'labor_pct_of_revenue', 'materials_pct_of_revenue'
    ]

    # Only include columns that exist
    column_order = [c for c in column_order if c in df.columns]
    df = df[column_order]

    return df


def create_training_features(profitability_df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform profitability data into features suitable for ML training.

    This creates the bridge between historical actuals and quote prediction.
    """
    df = profitability_df.copy()

    # The target variable for quote prediction is the sales_revenue (quoted price)
    df['quote_price'] = df['sales_revenue']

    # Create cost-based features that could predict quote price
    # These are derived from actuals but represent the cost structure

    # Material costs as feature
    df['material_cost'] = df['total_cogs']

    # Labor cost as feature
    df['labor_cost'] = df['hourly_costs']

    # Delivery/shipping costs
    df['delivery_cost'] = df['freight_delivery'] + df['shipping_delivery'] + df['freight_delivery_cos']

    # Department breakdown (indicates job type/complexity)
    df['has_metal_work'] = (df['metal_dept_supplies'] > 0).astype(int)
    df['has_wood_work'] = (df['wood_dept_supplies'] > 0).astype(int)
    df['has_finishing'] = (df['finish_dept_supplies'] > 0).astype(int)
    df['has_powder_coating'] = (df['powder_coating'] > 0).astype(int)

    # Complexity indicators
    df['num_departments'] = df['has_metal_work'] + df['has_wood_work'] + df['has_finishing'] + df['has_powder_coating']

    # Cost ratios (useful for understanding job structure)
    df['labor_to_material_ratio'] = df.apply(
        lambda r: r['labor_cost'] / r['material_cost'] if r['material_cost'] > 0 else 0, axis=1
    )

    return df


if __name__ == '__main__':
    # Default to the project root directory
    project_root = Path(__file__).parent.parent.parent

    print("=" * 60)
    print("B10 Union LLC Profitability Data Ingestion")
    print("=" * 60)

    # Parse all profitability files
    df = ingest_all_profitability_files(str(project_root))

    if len(df) > 0:
        print(f"\nSuccessfully parsed {len(df)} profitability reports.")

        # Save raw profitability data
        output_path = project_root / 'data' / 'profitability_data.csv'
        output_path.parent.mkdir(exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Saved to: {output_path}")

        # Create training features
        training_df = create_training_features(df)
        training_output = project_root / 'data' / 'training_features.csv'
        training_df.to_csv(training_output, index=False)
        print(f"Training features saved to: {training_output}")

        # Display summary
        print("\n" + "=" * 60)
        print("SUMMARY STATISTICS")
        print("=" * 60)
        print(f"\nProjects analyzed: {len(df)}")
        print(f"Total revenue: ${df['total_income'].sum():,.2f}")
        print(f"Average project size: ${df['total_income'].mean():,.2f}")
        print(f"Average gross margin: {df['gross_margin_pct'].mean():.1f}%")
        print(f"Average net margin: {df['net_margin_pct'].mean():.1f}%")
        print(f"Average labor % of revenue: {df['labor_pct_of_revenue'].mean():.1f}%")
        print(f"Average materials % of revenue: {df['materials_pct_of_revenue'].mean():.1f}%")

        print("\n" + "=" * 60)
        print("PROJECT DETAILS")
        print("=" * 60)
        for _, row in df.iterrows():
            print(f"\n{row['project']}")
            print(f"  Revenue: ${row['total_income']:,.2f}")
            print(f"  COGS: ${row['total_cogs']:,.2f}")
            print(f"  Labor: ${row['hourly_costs']:,.2f}")
            print(f"  Gross Margin: {row['gross_margin_pct']:.1f}%")
            print(f"  Net Margin: {row['net_margin_pct']:.1f}%")

        # Also merge with the existing woodworking_quotes.csv for more features
        print("\n" + "=" * 60)
        print("MERGING WITH EXISTING QUOTE DATA")
        print("=" * 60)
        existing_quotes_path = project_root / 'woodworking_quotes.csv'
        if existing_quotes_path.exists():
            existing_df = pd.read_csv(existing_quotes_path)
            print(f"Found {len(existing_df)} existing quote records")
            # Combine both datasets for a richer training set
            combined_output = project_root / 'data' / 'combined_quotes.csv'
            existing_df.to_csv(combined_output, index=False)
            print(f"Existing quotes saved to: {combined_output}")
    else:
        print("No data parsed. Check that text files exist in the project directory.")
