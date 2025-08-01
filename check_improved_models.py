import pickle
import pandas as pd
import numpy as np

# Load improved models
print("Loading improved models...")
try:
    with open('models_improved/future_predictions.pkl', 'rb') as f:
        future_predictions = pickle.load(f)
    print("✓ future_predictions loaded")
    
    with open('models_improved/model_results.pkl', 'rb') as f:
        model_results = pickle.load(f)
    print("✓ model_results loaded")
except Exception as e:
    print(f"Error loading models: {e}")
    exit()

# Check structure
print("\n" + "="*50)
print("FUTURE PREDICTIONS STRUCTURE")
print("="*50)

for sku, predictions in future_predictions.items():
    print(f"\nSKU: {sku}")
    print(f"Keys: {list(predictions.keys())}")
    if 'arima' in predictions:
        arima_pred = predictions['arima']
        print(f"ARIMA predictions: {arima_pred}")
        print(f"Total: {np.sum(arima_pred)}")
    if 'forecast_months' in predictions:
        print(f"Forecast months: {predictions['forecast_months']}")

# Check VIT-C-1000 specifically
print("\n" + "="*50)
print("VIT-C-1000 DETAILED ANALYSIS")
print("="*50)

if 'VIT-C-1000' in future_predictions:
    vitc = future_predictions['VIT-C-1000']
    print(f"All keys: {list(vitc.keys())}")
    print(f"ARIMA predictions: {vitc.get('arima')}")
    print(f"Prophet predictions: {vitc.get('prophet')}")
    print(f"Best model: {vitc.get('best_model')}")
    print(f"Last date: {vitc.get('last_date')}")
    print(f"Forecast months: {vitc.get('forecast_months')}")
else:
    print("VIT-C-1000 not found in predictions!")

# Check model results structure
print("\n" + "="*50)
print("MODEL RESULTS STRUCTURE")
print("="*50)

for sku in model_results:
    print(f"\nSKU: {sku}")
    print(f"Keys: {list(model_results[sku].keys())}")