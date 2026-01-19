"""
Data preparation pipeline for woodworking quote prediction.

This module handles:
- Loading and merging data sources
- Feature engineering
- Train/validation/test splits
- Data export for ML training
"""

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from typing import Tuple, Dict, Any
import json


def load_all_data(data_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    Load all available data sources.

    Returns:
        Dictionary of dataframes by source type
    """
    data = {}

    # Load profitability data
    prof_path = data_dir / 'profitability_data.csv'
    if prof_path.exists():
        data['profitability'] = pd.read_csv(prof_path)
        print(f"Loaded profitability data: {len(data['profitability'])} records")

    # Load existing quotes
    quotes_path = data_dir / 'combined_quotes.csv'
    if quotes_path.exists():
        data['quotes'] = pd.read_csv(quotes_path)
        print(f"Loaded quotes data: {len(data['quotes'])} records")

    # Load synthetic data (for development/testing)
    synthetic_path = data_dir.parent / 'woodworking_quotes_synthetic_random.csv'
    if synthetic_path.exists():
        data['synthetic'] = pd.read_csv(synthetic_path)
        print(f"Loaded synthetic data: {len(data['synthetic'])} records")

    return data


def engineer_features(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Engineer features appropriate for the data source.

    Args:
        df: Source dataframe
        source: Data source type ('profitability', 'quotes', 'synthetic')

    Returns:
        Dataframe with engineered features
    """
    df = df.copy()

    if source == 'profitability':
        # Target variable
        df['quote_price'] = df['total_income']

        # Cost components
        df['material_cost'] = df['total_cogs']
        df['labor_cost'] = df['hourly_costs']
        df['delivery_cost'] = (
            df['freight_delivery'].fillna(0) +
            df['shipping_delivery'].fillna(0) +
            df['freight_delivery_cos'].fillna(0)
        )

        # Job characteristics from cost structure
        df['has_metal_work'] = (df['metal_dept_supplies'] > 0).astype(int)
        df['has_wood_work'] = (df['wood_dept_supplies'] > 0).astype(int)
        df['has_finishing'] = (df['finish_dept_supplies'] > 0).astype(int)
        df['has_powder_coating'] = (df['powder_coating'] > 0).astype(int)
        df['has_upholstery'] = (df.get('upholstery_cost', pd.Series([0]*len(df))) > 0).astype(int)

        # Complexity
        df['num_work_types'] = (
            df['has_metal_work'] +
            df['has_wood_work'] +
            df['has_finishing'] +
            df['has_powder_coating'] +
            df['has_upholstery']
        )

        # Cost ratios
        df['labor_ratio'] = df['labor_cost'] / df['quote_price'].replace(0, np.nan)
        df['material_ratio'] = df['material_cost'] / df['quote_price'].replace(0, np.nan)

        # Volume indicator (derived from material cost per department)
        df['avg_dept_cost'] = df['material_cost'] / df['num_work_types'].replace(0, 1)

    elif source in ['quotes', 'synthetic']:
        # Calculate volume from dimensions
        if all(c in df.columns for c in ['length_in', 'width_in', 'height_in']):
            df['volume_cubic_in'] = df['length_in'] * df['width_in'] * df['height_in']
            df['surface_area_sq_in'] = 2 * (
                df['length_in'] * df['width_in'] +
                df['width_in'] * df['height_in'] +
                df['height_in'] * df['length_in']
            )

        # Total job size
        if 'quantity' in df.columns:
            df['total_volume'] = df.get('volume_cubic_in', 0) * df['quantity']

        # Labor intensity
        if 'estimated_labor_hours' in df.columns and 'quote_price' in df.columns:
            df['labor_per_dollar'] = df['estimated_labor_hours'] / df['quote_price'].replace(0, np.nan)

        # Complexity features
        if 'finishing_complexity' in df.columns:
            df['high_complexity'] = (df['finishing_complexity'] >= 4).astype(int)

        # Installation indicator
        if 'installation_required' in df.columns:
            df['installation_required'] = df['installation_required'].apply(
                lambda x: 1 if str(x).lower() in ['yes', '1', 'true', 1] else 0
            )

    # Fill NaN values
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)

    return df


def prepare_training_data(
    data: Dict[str, pd.DataFrame],
    use_synthetic: bool = True,
    test_size: float = 0.2,
    val_size: float = 0.1,
    random_state: int = 42
) -> Dict[str, pd.DataFrame]:
    """
    Prepare train/validation/test splits.

    Args:
        data: Dictionary of dataframes by source
        use_synthetic: Whether to include synthetic data
        test_size: Proportion for test set
        val_size: Proportion for validation set (from remaining after test)
        random_state: Random seed for reproducibility

    Returns:
        Dictionary with train, val, test dataframes
    """
    all_records = []

    # Process profitability data
    if 'profitability' in data:
        prof_df = engineer_features(data['profitability'], 'profitability')
        prof_df['data_source'] = 'profitability'
        all_records.append(prof_df)
        print(f"Added {len(prof_df)} profitability records")

    # Process quotes data
    if 'quotes' in data:
        quotes_df = engineer_features(data['quotes'], 'quotes')
        quotes_df['data_source'] = 'quotes'
        all_records.append(quotes_df)
        print(f"Added {len(quotes_df)} quote records")

    # Optionally add synthetic data
    if use_synthetic and 'synthetic' in data:
        synthetic_df = engineer_features(data['synthetic'], 'synthetic')
        synthetic_df['data_source'] = 'synthetic'
        all_records.append(synthetic_df)
        print(f"Added {len(synthetic_df)} synthetic records")

    if not all_records:
        raise ValueError("No data available for training")

    # Combine all data
    combined_df = pd.concat(all_records, ignore_index=True)
    print(f"\nTotal combined records: {len(combined_df)}")

    # Ensure quote_price exists and is valid
    if 'quote_price' not in combined_df.columns:
        raise ValueError("quote_price column not found in data")

    combined_df = combined_df[combined_df['quote_price'] > 0]
    print(f"Records with valid quote_price: {len(combined_df)}")

    # Split data
    # First split: separate test set
    train_val_df, test_df = train_test_split(
        combined_df,
        test_size=test_size,
        random_state=random_state
    )

    # Second split: separate validation from training
    actual_val_size = val_size / (1 - test_size)  # Adjust for remaining data
    train_df, val_df = train_test_split(
        train_val_df,
        test_size=actual_val_size,
        random_state=random_state
    )

    print(f"\nSplit sizes:")
    print(f"  Train: {len(train_df)} ({len(train_df)/len(combined_df)*100:.1f}%)")
    print(f"  Validation: {len(val_df)} ({len(val_df)/len(combined_df)*100:.1f}%)")
    print(f"  Test: {len(test_df)} ({len(test_df)/len(combined_df)*100:.1f}%)")

    return {
        'train': train_df,
        'val': val_df,
        'test': test_df,
        'combined': combined_df
    }


def get_feature_columns(df: pd.DataFrame) -> Tuple[list, list]:
    """
    Identify numeric and categorical feature columns.

    Returns:
        Tuple of (numeric_columns, categorical_columns)
    """
    # Columns to exclude
    exclude_cols = {
        'quote_price',  # Target
        'project', 'project_name', 'customer_name',  # Identifiers
        'source_file', 'data_source',  # Metadata
        'estimator_notes', 'job_description',  # Free text
    }

    numeric_cols = []
    categorical_cols = []

    for col in df.columns:
        if col in exclude_cols:
            continue

        if df[col].dtype in ['object', 'category']:
            categorical_cols.append(col)
        elif df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
            # Check if it's actually categorical (few unique values)
            if df[col].nunique() <= 10 and col not in ['quantity', 'finishing_complexity']:
                categorical_cols.append(col)
            else:
                numeric_cols.append(col)

    return numeric_cols, categorical_cols


def save_splits(
    splits: Dict[str, pd.DataFrame],
    output_dir: Path,
    prefix: str = ''
) -> None:
    """Save train/val/test splits to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for split_name, df in splits.items():
        filename = f"{prefix}{split_name}.csv" if prefix else f"{split_name}.csv"
        output_path = output_dir / filename
        df.to_csv(output_path, index=False)
        print(f"Saved {split_name} to {output_path}")

    # Save metadata
    metadata = {
        'num_train': len(splits.get('train', [])),
        'num_val': len(splits.get('val', [])),
        'num_test': len(splits.get('test', [])),
        'num_total': len(splits.get('combined', [])),
    }

    if 'combined' in splits:
        numeric_cols, cat_cols = get_feature_columns(splits['combined'])
        metadata['numeric_features'] = numeric_cols
        metadata['categorical_features'] = cat_cols

    metadata_path = output_dir / 'data_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {metadata_path}")


def main():
    """Run the data preparation pipeline."""
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data'

    print("=" * 60)
    print("Woodworking Quote Data Preparation Pipeline")
    print("=" * 60)

    # Load data
    print("\n--- Loading Data ---")
    data = load_all_data(data_dir)

    if not data:
        print("No data found. Please run the ingestion script first.")
        return

    # Prepare training splits
    print("\n--- Preparing Training Data ---")
    splits = prepare_training_data(
        data,
        use_synthetic=True,  # Include synthetic for now (limited real data)
        test_size=0.2,
        val_size=0.1
    )

    # Save splits
    print("\n--- Saving Data Splits ---")
    processed_dir = data_dir / 'processed'
    save_splits(splits, processed_dir)

    # Summary statistics
    print("\n" + "=" * 60)
    print("DATA SUMMARY")
    print("=" * 60)

    train_df = splits['train']

    print(f"\nQuote Price Statistics (Training Set):")
    print(f"  Min: ${train_df['quote_price'].min():,.2f}")
    print(f"  Max: ${train_df['quote_price'].max():,.2f}")
    print(f"  Mean: ${train_df['quote_price'].mean():,.2f}")
    print(f"  Median: ${train_df['quote_price'].median():,.2f}")
    print(f"  Std Dev: ${train_df['quote_price'].std():,.2f}")

    print(f"\nData Sources:")
    for source, count in train_df['data_source'].value_counts().items():
        print(f"  {source}: {count} records")

    # Feature summary
    numeric_cols, cat_cols = get_feature_columns(train_df)
    print(f"\nFeature Counts:")
    print(f"  Numeric: {len(numeric_cols)}")
    print(f"  Categorical: {len(cat_cols)}")

    print("\n" + "=" * 60)
    print("Data preparation complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
