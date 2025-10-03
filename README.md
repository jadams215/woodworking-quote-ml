📄 Full README Content 
# 🪚 Woodworking Quote Prediction Model (In Progress)

This project is an experiment in using **machine learning** (CatBoost) to predict woodworking job quotes.  
Since real historical job data is not yet available, the current version uses **synthetic random data** for testing.

---

## 📂 Project Status
- ✅ Synthetic dataset generated (100 random jobs between $500 – $500,000)
- ✅ Training pipeline with CatBoost (`train_catboost.py`)
- ✅ Model evaluation with RMSE & R²
- ✅ Visualizations (`analyze_model.py`) for feature importance, predicted vs actual, and error distribution
- ⏳ Awaiting real data to replace synthetic dataset
- ⏳ Interactive predictions (`predict_quote.py`) planned but not implemented yet

---

## 🚀 How to Run

### 1. Train the model
Run the training script on the synthetic dataset:
```bash
python train_catboost.py


This will:

Load the synthetic CSV

Train a CatBoost regression model

Print metrics (RMSE, R²)

Save the model file wood_quote_model.cbm

2. Analyze results

Run:

python analyze_model.py


This will:

Reload the trained model and dataset

Print performance metrics

Generate and save plots:

feature_importance.png

predicted_vs_actual.png

error_histogram.png

📊 Example Results (Synthetic Data)

Model Performance:

RMSE: ~136,000
R²: ~0.07


(Low accuracy expected since data is random noise — this will improve with real job data.)

📊 Visualizations

Feature Importance


Predicted vs Actual


Error Distribution


🛠 Tech Stack

Python 3.10+

Pandas for data handling

Scikit-learn for metrics

CatBoost for modeling

Matplotlib for plots

📌 Next Steps

Replace synthetic data with real woodworking job dataset

Implement interactive quoting tool (predict_quote.py)

Compare CatBoost with XGBoost and Random Forest

Clean and standardize real-world inputs (wood species, install flag, dimensions)

Consider deployment as a small API or quoting assistant

👤 Author

James Adams
Exploring practical ML for small business operations, starting with woodworking job
