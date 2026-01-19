"""
ML-based Cost Adjustment Model.

This model learns to predict the delta between the deterministic should-cost
model and actual quoted prices. It captures:
- Market pricing factors
- Estimator judgment patterns
- Customer-specific adjustments
- Complexity factors not captured in cost tables
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import json
import pickle
from dataclasses import dataclass

from catboost import CatBoostRegressor, Pool
from sklearn.model_selection import cross_val_score, KFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    rmse: float
    mae: float
    mape: float
    r2: float
    cv_rmse_mean: float
    cv_rmse_std: float

    def to_dict(self) -> Dict[str, float]:
        return {
            'rmse': self.rmse,
            'mae': self.mae,
            'mape': self.mape,
            'r2': self.r2,
            'cv_rmse_mean': self.cv_rmse_mean,
            'cv_rmse_std': self.cv_rmse_std,
        }


class MLCostAdjuster:
    """
    Machine learning model to adjust should-cost estimates.

    Uses CatBoost regression to learn pricing patterns from historical data.
    """

    # Features to use for training
    NUMERIC_FEATURES = [
        'estimated_labor_hours',
        'estimated_machine_hours',
        'length_in',
        'width_in',
        'height_in',
        'quantity',
        'delivery_miles',
        'hardware_cost',
        'finish_material_cost',
        'job_complexity_score',
        'risk_adjustment_pct',
        'waste_factor_pct',
        'overhead_allocation',
        'finishing_complexity',
        # Derived features
        'volume_cubic_in',
        'surface_area_sq_in',
        'total_volume',
        # From profitability data
        'labor_cost',
        'material_cost',
        'delivery_cost',
        'num_work_types',
        'labor_ratio',
        'material_ratio',
    ]

    CATEGORICAL_FEATURES = [
        'wood_species',
        'material_grade',
        'installation_required',
        'has_metal_work',
        'has_wood_work',
        'has_finishing',
        'has_powder_coating',
        'has_upholstery',
    ]

    def __init__(
        self,
        model_params: Optional[Dict[str, Any]] = None,
        feature_importance_threshold: float = 0.01
    ):
        """
        Initialize the ML adjuster.

        Args:
            model_params: CatBoost parameters (uses defaults if not provided)
            feature_importance_threshold: Minimum importance to keep a feature
        """
        self.model_params = model_params or {
            'iterations': 1000,
            'learning_rate': 0.05,
            'depth': 6,
            'loss_function': 'RMSE',
            'random_seed': 42,
            'verbose': 100,
            'early_stopping_rounds': 50,
        }

        self.feature_importance_threshold = feature_importance_threshold
        self.model: Optional[CatBoostRegressor] = None
        self.feature_columns: List[str] = []
        self.cat_feature_indices: List[int] = []
        self.metrics: Optional[ModelMetrics] = None
        self.feature_importances: Dict[str, float] = {}

    def _prepare_features(
        self,
        df: pd.DataFrame,
        fit: bool = False
    ) -> Tuple[pd.DataFrame, List[int]]:
        """
        Prepare features for training or prediction.

        Args:
            df: Input dataframe
            fit: If True, determine feature columns from data

        Returns:
            Tuple of (feature DataFrame, categorical feature indices)
        """
        # Determine available features
        available_numeric = [f for f in self.NUMERIC_FEATURES if f in df.columns]
        available_categorical = [f for f in self.CATEGORICAL_FEATURES if f in df.columns]

        if fit:
            self.feature_columns = available_numeric + available_categorical
            self.cat_feature_indices = list(range(
                len(available_numeric),
                len(available_numeric) + len(available_categorical)
            ))

        # For prediction, we need to match the trained feature columns
        # Handle case where prediction data has fewer features than training
        if not fit and self.feature_columns:
            # Create a dataframe with all expected features
            features = pd.DataFrame(index=df.index)

            # Track which features are actually categorical in the final set
            final_cat_indices = []

            for i, col in enumerate(self.feature_columns):
                if col in df.columns:
                    features[col] = df[col]
                else:
                    # Fill missing features with defaults
                    if i in self.cat_feature_indices:
                        features[col] = 'Unknown'
                    else:
                        features[col] = 0

                # Track categorical indices
                if i in self.cat_feature_indices:
                    final_cat_indices.append(len(features.columns) - 1)

            # Fill NaN values
            for i, col in enumerate(self.feature_columns):
                if i in self.cat_feature_indices:
                    features[col] = features[col].fillna('Unknown').astype(str)
                else:
                    features[col] = pd.to_numeric(features[col], errors='coerce').fillna(0)

            return features, self.cat_feature_indices

        # For training (fit=True), use only available features
        features = df[self.feature_columns].copy() if self.feature_columns else df[available_numeric + available_categorical].copy()

        # Fill missing values
        for col in available_numeric:
            if col in features.columns:
                features[col] = features[col].fillna(0)

        for col in available_categorical:
            if col in features.columns:
                features[col] = features[col].fillna('Unknown').astype(str)

        return features, self.cat_feature_indices

    def train(
        self,
        train_df: pd.DataFrame,
        val_df: Optional[pd.DataFrame] = None,
        target_col: str = 'quote_price'
    ) -> ModelMetrics:
        """
        Train the model.

        Args:
            train_df: Training data
            val_df: Validation data (optional)
            target_col: Name of target column

        Returns:
            ModelMetrics with performance statistics
        """
        print("Preparing training features...")

        # Prepare features
        X_train, cat_indices = self._prepare_features(train_df, fit=True)
        y_train = train_df[target_col]

        print(f"Training with {len(X_train)} samples, {len(self.feature_columns)} features")
        print(f"  Numeric features: {len(self.feature_columns) - len(cat_indices)}")
        print(f"  Categorical features: {len(cat_indices)}")

        # Create pools
        train_pool = Pool(X_train, y_train, cat_features=cat_indices)

        eval_set = None
        if val_df is not None and len(val_df) > 0:
            X_val, _ = self._prepare_features(val_df, fit=False)
            y_val = val_df[target_col]
            eval_set = Pool(X_val, y_val, cat_features=cat_indices)

        # Initialize and train model
        self.model = CatBoostRegressor(**self.model_params)
        self.model.fit(
            train_pool,
            eval_set=eval_set,
            use_best_model=eval_set is not None
        )

        # Calculate metrics
        print("\nCalculating metrics...")

        # Training predictions
        train_preds = self.model.predict(train_pool)

        # Cross-validation using CatBoost's built-in CV
        # (sklearn's cross_val_score doesn't handle cat_features properly)
        try:
            from catboost import cv as catboost_cv
            cv_data = train_pool
            cv_params = self.model_params.copy()
            cv_params['verbose'] = False
            cv_results = catboost_cv(
                cv_data,
                cv_params,
                fold_count=min(5, len(X_train) // 2),
                shuffle=True,
                partition_random_seed=42,
            )
            cv_rmse_values = cv_results['test-RMSE-mean'].values
            cv_scores = -cv_rmse_values  # Negate to match sklearn convention
        except Exception as e:
            print(f"CV failed: {e}, using training metrics only")
            cv_scores = np.array([-np.sqrt(mean_squared_error(y_train, train_preds))])

        self.metrics = ModelMetrics(
            rmse=np.sqrt(mean_squared_error(y_train, train_preds)),
            mae=mean_absolute_error(y_train, train_preds),
            mape=np.mean(np.abs((y_train - train_preds) / y_train.clip(lower=1))) * 100,
            r2=r2_score(y_train, train_preds),
            cv_rmse_mean=np.abs(cv_scores).mean() if len(cv_scores) > 0 else 0,
            cv_rmse_std=np.abs(cv_scores).std() if len(cv_scores) > 1 else 0,
        )

        # Feature importances
        importances = self.model.get_feature_importance(train_pool)
        self.feature_importances = dict(zip(self.feature_columns, importances))
        self.feature_importances = dict(sorted(
            self.feature_importances.items(),
            key=lambda x: x[1],
            reverse=True
        ))

        return self.metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """
        Make predictions.

        Args:
            df: Input dataframe

        Returns:
            Array of predictions
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")

        X, _ = self._prepare_features(df, fit=False)
        return self.model.predict(X)

    def predict_with_uncertainty(
        self,
        df: pd.DataFrame,
        n_iterations: int = 100
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions with uncertainty estimates using virtual ensembles.

        Args:
            df: Input dataframe
            n_iterations: Number of virtual ensemble iterations

        Returns:
            Tuple of (predictions, standard deviations)
        """
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")

        X, _ = self._prepare_features(df, fit=False)

        # Use CatBoost's virtual ensembles for uncertainty
        predictions = self.model.predict(X)

        # Estimate uncertainty from tree variance (simplified)
        # In production, use proper Bayesian or ensemble methods
        tree_preds = []
        for i in range(0, self.model.tree_count_, max(1, self.model.tree_count_ // 10)):
            tree_preds.append(self.model.predict(X, ntree_end=i+1))

        if len(tree_preds) > 1:
            std_devs = np.std(tree_preds, axis=0)
        else:
            std_devs = np.zeros(len(predictions))

        return predictions, std_devs

    def evaluate(
        self,
        test_df: pd.DataFrame,
        target_col: str = 'quote_price'
    ) -> Dict[str, float]:
        """
        Evaluate model on test data.

        Args:
            test_df: Test dataframe
            target_col: Target column name

        Returns:
            Dictionary of metrics
        """
        y_test = test_df[target_col]
        y_pred = self.predict(test_df)

        return {
            'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
            'mae': mean_absolute_error(y_test, y_pred),
            'mape': np.mean(np.abs((y_test - y_pred) / y_test.clip(lower=1))) * 100,
            'r2': r2_score(y_test, y_pred),
        }

    def save(self, model_dir: Path) -> None:
        """Save model and metadata."""
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save CatBoost model
        if self.model:
            self.model.save_model(str(model_dir / 'catboost_model.cbm'))

        # Save metadata
        metadata = {
            'feature_columns': self.feature_columns,
            'cat_feature_indices': self.cat_feature_indices,
            'feature_importances': self.feature_importances,
            'metrics': self.metrics.to_dict() if self.metrics else None,
            'model_params': self.model_params,
        }
        with open(model_dir / 'model_metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"Model saved to {model_dir}")

    def load(self, model_dir: Path) -> None:
        """Load model and metadata."""
        # Load CatBoost model
        self.model = CatBoostRegressor()
        self.model.load_model(str(model_dir / 'catboost_model.cbm'))

        # Load metadata
        with open(model_dir / 'model_metadata.json', 'r') as f:
            metadata = json.load(f)

        self.feature_columns = metadata['feature_columns']
        self.cat_feature_indices = metadata['cat_feature_indices']
        self.feature_importances = metadata['feature_importances']
        self.model_params = metadata['model_params']

        if metadata['metrics']:
            self.metrics = ModelMetrics(**metadata['metrics'])

        print(f"Model loaded from {model_dir}")

    def print_feature_importances(self, top_n: int = 15) -> None:
        """Print top feature importances."""
        print("\nTop Feature Importances:")
        print("-" * 40)
        for i, (feature, importance) in enumerate(self.feature_importances.items()):
            if i >= top_n:
                break
            print(f"  {feature:30s} {importance:8.2f}")


def train_adjustment_model(
    data_dir: Path,
    output_dir: Path,
    use_synthetic: bool = True
) -> MLCostAdjuster:
    """
    Train the ML adjustment model.

    Args:
        data_dir: Directory containing processed data
        output_dir: Directory to save model
        use_synthetic: Whether to include synthetic data

    Returns:
        Trained MLCostAdjuster
    """
    print("=" * 60)
    print("Training ML Cost Adjustment Model")
    print("=" * 60)

    # Load data
    train_path = data_dir / 'processed' / 'train.csv'
    val_path = data_dir / 'processed' / 'val.csv'
    test_path = data_dir / 'processed' / 'test.csv'

    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path)
    test_df = pd.read_csv(test_path)

    print(f"\nLoaded data:")
    print(f"  Train: {len(train_df)} samples")
    print(f"  Validation: {len(val_df)} samples")
    print(f"  Test: {len(test_df)} samples")

    # Optionally filter out synthetic data
    if not use_synthetic:
        train_df = train_df[train_df['data_source'] != 'synthetic']
        val_df = val_df[val_df['data_source'] != 'synthetic']
        test_df = test_df[test_df['data_source'] != 'synthetic']
        print(f"\nAfter removing synthetic data:")
        print(f"  Train: {len(train_df)} samples")
        print(f"  Validation: {len(val_df)} samples")
        print(f"  Test: {len(test_df)} samples")

    # Initialize and train model
    model = MLCostAdjuster()
    metrics = model.train(train_df, val_df)

    print("\n" + "=" * 60)
    print("TRAINING RESULTS")
    print("=" * 60)
    print(f"\nTraining Metrics:")
    print(f"  RMSE: ${metrics.rmse:,.2f}")
    print(f"  MAE: ${metrics.mae:,.2f}")
    print(f"  MAPE: {metrics.mape:.1f}%")
    print(f"  R²: {metrics.r2:.4f}")
    print(f"\nCross-Validation RMSE: ${metrics.cv_rmse_mean:,.2f} (±${metrics.cv_rmse_std:,.2f})")

    model.print_feature_importances()

    # Evaluate on test set
    if len(test_df) > 0:
        print("\n" + "-" * 40)
        print("Test Set Evaluation:")
        test_metrics = model.evaluate(test_df)
        print(f"  RMSE: ${test_metrics['rmse']:,.2f}")
        print(f"  MAE: ${test_metrics['mae']:,.2f}")
        print(f"  MAPE: {test_metrics['mape']:.1f}%")
        print(f"  R²: {test_metrics['r2']:.4f}")

    # Save model
    model.save(output_dir / 'ml_adjuster')

    return model


if __name__ == '__main__':
    project_root = Path(__file__).parent.parent.parent
    data_dir = project_root / 'data'
    model_dir = project_root / 'models'

    model = train_adjustment_model(
        data_dir=data_dir,
        output_dir=model_dir,
        use_synthetic=True  # Include synthetic data for now
    )
