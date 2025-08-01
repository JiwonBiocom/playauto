import pickle
import numpy as np
import pandas as pd

# Load predictions and results
with open('models/future_predictions.pkl', 'rb') as f:
    future_predictions = pickle.load(f)

with open('models/model_results.pkl', 'rb') as f:
    model_results = pickle.load(f)

print("SCALE COMPARISON - DAILY TRAINING")
print("="*60)

for sku in ['VIT-C-1000', 'PROBIO-10B', 'CALCIUM-MAG']:
    print(f"\n{sku}:")
    
    # Check training data scale
    if sku in model_results and 30 in model_results[sku]:
        train_info = model_results[sku][30]
        print(f"  Training size: {train_info.get('train_size', 'N/A')} days")
        print(f"  Non-zero training days: {train_info.get('non_zero_train', 'N/A')}")
    
    # Check predictions
    if sku in future_predictions and 30 in future_predictions[sku]:
        pred = future_predictions[sku][30]['arima']
        daily_mean = np.mean(pred)
        monthly_total = np.sum(pred)  # 30 days of predictions
        
        print(f"  Daily prediction mean: {daily_mean:.4f}")
        print(f"  30-day total: {monthly_total:.2f}")
        print(f"  Approx monthly (x30): {daily_mean * 30:.2f}")
        
        # Show actual values if available
        if 'arima' in model_results[sku][30]:
            actual_test = model_results[sku][30]['arima'].get('forecast', [])
            if len(actual_test) > 0:
                print(f"  Test period mean: {np.mean(actual_test):.2f}")

print("\n\nPOSSIBLE ISSUES:")
print("1. Daily data with many zeros causing ARIMA to predict near-zero")
print("2. Need to use log transformation or other preprocessing")
print("3. ARIMA order (1,1,1) might be too simple for daily patterns")