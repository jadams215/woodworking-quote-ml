import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from catboost import CatBoostRegressor, Pool
from math import sqrt
import os

# Path to your dataset
csv_path = r"C:\Users\jadam\OneDrive\Desktop\AI Modeling\Ben Biz Files\woodworking_quotes_synthetic_random.csv"

if not os.path.exists(csv_path):
    raise FileNotFoundError(f"CSV not found at {csv_path}")

# Load dataset
df = pd.read_csv(csv_path)

# Target = what we want to predict
y = df["quote_price"]

# Features = everything else except ID, customer name, and notes (not numeric for now)
X = df.drop(columns=["quote_price", "job_id", "customer_name", "estimator_notes"])

# Detect categorical columns (strings like wood_species, material_grade, Yes/No)
cat_cols = X.select_dtypes(include=["object"]).columns.tolist()
cat_idx = [X.columns.get_loc(c) for c in cat_cols]

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Define CatBoost model
model = CatBoostRegressor(
    iterations=2000,
    learning_rate=0.05,
    depth=6,
    loss_function="RMSE",
    random_seed=42,
    verbose=200
)

# Train
train_pool = Pool(X_train, label=y_train, cat_features=cat_idx)
test_pool = Pool(X_test, label=y_test, cat_features=cat_idx)

model.fit(train_pool, eval_set=test_pool, early_stopping_rounds=100, use_best_model=True)

# Evaluate
preds = model.predict(test_pool)

# RMSE
rmse = sqrt(mean_squared_error(y_test, preds))
print("\n=== Model Performance ===")
print("RMSE:", rmse)

# R² score
from sklearn.metrics import r2_score
r2 = r2_score(y_test, preds)
print("R²:", r2)

# === Visualization ===
import matplotlib.pyplot as plt

# Scatterplot of predicted vs actual
plt.figure(figsize=(8, 6))
plt.scatter(y_test, preds, alpha=0.6, color="teal")
plt.plot([y_test.min(), y_test.max()], [y_test.min(), y_test.max()], "r--")  # ideal fit line
plt.xlabel("Actual Quote Price")
plt.ylabel("Predicted Quote Price")
plt.title("Predicted vs Actual Quote Prices")
plt.show()


# Feature importance
importances = model.get_feature_importance(train_pool)
fi = pd.DataFrame({"feature": X.columns, "importance": importances}).sort_values("importance", ascending=False)
print("\n=== Top Features ===")
print(fi.head(10))
import matplotlib.pyplot as plt

# Plot top 10 features
plt.figure(figsize=(10, 6))
plt.barh(fi["feature"].head(10), fi["importance"].head(10), color="skyblue")
plt.xlabel("Importance Score")
plt.title("Top 10 Feature Importances (CatBoost)")
plt.gca().invert_yaxis()  # Highest at top
plt.show()


# Save trained model
model.save_model("wood_quote_model.cbm")
print("\n✅ Model saved as wood_quote_model.cbm")
