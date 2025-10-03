import pandas as pd
import os

# Path to your synthetic dataset
csv_path = r"C:\Users\jadam\OneDrive\Desktop\AI Modeling\Ben Biz Files\woodworking_quotes_synthetic_random.csv"

# Check if file exists
if not os.path.exists(csv_path):
    raise FileNotFoundError(f"CSV not found at {csv_path}\n"
                            f"👉 Make sure the file is there or update the path in the script.")

# Load dataset
df = pd.read_csv(csv_path)

print("\n=== Quick Overview ===")
print(df.head())
print("\nShape:", df.shape)

print("\n=== Quote Price Summary ===")
print(df["quote_price"].describe())

print("\n=== Average Quote by Wood Species ===")
print(df.groupby("wood_species")["quote_price"].mean().sort_values(ascending=False))

print("\n=== Average Quote by Installation Required ===")
print(df.groupby("installation_required")["quote_price"].mean())

print("\n=== Correlation with Quote Price (numerical only) ===")
numeric_cols = df.select_dtypes(include=["int64", "float64"]).columns
corr = df[numeric_cols].corr()["quote_price"].sort_values(ascending=False)
print(corr)

print("\n=== Top 10 Most Expensive Jobs ===")
print(df[["job_id", "customer_name", "quote_price"]].sort_values("quote_price", ascending=False).head(10))

import pandas as pd
import os

# Path to your CSV file (same folder as script)
csv_path = r"C:\Users\jadam\OneDrive\Desktop\AI Modeling\Ben Biz Files\woodworking_quotes_synthetic_random.csv"

# Check if file exists
if not os.path.exists(csv_path):
    raise FileNotFoundError(f"CSV not found at {csv_path}")

# Load dataset
df = pd.read_csv(csv_path)

print("\n=== Quick Overview ===")
print(df.head())
print("\nShape:", df.shape)

print("\n=== Quote Price Summary ===")
print(df["quote_price"].describe())

print("\n=== Average Quote by Wood Species ===")
print(df.groupby("wood_species")["quote_price"].mean().sort_values(ascending=False))

print("\n=== Average Quote by Installation Required ===")
print(df.groupby("installation_required")["quote_price"].mean())

print("\n=== Correlation with Quote Price (numerical only) ===")
numeric_cols = df.select_dtypes(include=["int64", "float64"]).columns
corr = df[numeric_cols].corr()["quote_price"].sort_values(ascending=False)
print(corr)

print("\n=== Top 10 Most Expensive Jobs ===")
print(df[["job_id", "customer_name", "quote_price"]].sort_values("quote_price", ascending=False).head(10))

