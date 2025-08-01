import pickle
import numpy as np

# Load predictions
with open('models/future_predictions.pkl', 'rb') as f:
    future_predictions = pickle.load(f)

# Check VIT-C-1000 predictions
sku = 'VIT-C-1000'

print(f"Checking predictions for {sku}")
print("="*50)

if sku in future_predictions:
    for horizon in [30, 60, 90]:
        if horizon in future_predictions[sku]:
            pred_data = future_predictions[sku][horizon]
            arima_pred = pred_data.get('arima', [])
            
            print(f"\nHorizon: {horizon} days")
            print(f"Number of predictions: {len(arima_pred)}")
            print(f"Prediction values: {arima_pred[:10]}")  # First 10 values
            print(f"Sum of predictions: {np.sum(arima_pred)}")
            print(f"Mean of predictions: {np.mean(arima_pred):.2f}")
            print(f"Min: {np.min(arima_pred):.2f}, Max: {np.max(arima_pred):.2f}")
else:
    print(f"No predictions found for {sku}")

# Also check if the SKU was in training data
print("\n\nChecking all available SKUs:")
for sku in sorted(future_predictions.keys()):
    print(f"- {sku}")