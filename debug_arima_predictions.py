import pickle
import numpy as np
import pandas as pd

# Load saved results
with open('models/model_results.pkl', 'rb') as f:
    model_results = pickle.load(f)

with open('models/future_predictions.pkl', 'rb') as f:
    future_predictions = pickle.load(f)

# Problematic SKUs
problematic_skus = ['PROBIO-10B', 'VIT-D-5000', 'LUTEIN-20']
normal_skus = ['CALCIUM-MAG', 'ZINC-15']

print("="*60)
print("DEBUGGING ARIMA PREDICTIONS")
print("="*60)

for sku in problematic_skus + normal_skus:
    print(f"\n{'='*50}")
    print(f"SKU: {sku}")
    print('='*50)
    
    if sku not in model_results:
        print(f"No results for {sku}")
        continue
    
    for horizon in [30, 60, 90]:
        if horizon not in model_results[sku]:
            continue
            
        results = model_results[sku][horizon]
        
        if 'arima' in results:
            arima_data = results['arima']
            forecast = arima_data['forecast']
            
            print(f"\nHorizon: {horizon} days")
            print(f"Forecast length: {len(forecast)}")
            print(f"Forecast mean: {np.mean(forecast):.4f}")
            print(f"Forecast std: {np.std(forecast):.4f}")
            print(f"Forecast min: {np.min(forecast):.4f}")
            print(f"Forecast max: {np.max(forecast):.4f}")
            
            # Check for near-zero predictions
            near_zero = np.sum(np.abs(forecast) < 0.01)
            negative = np.sum(forecast < 0)
            
            print(f"Near-zero predictions (<0.01): {near_zero}")
            print(f"Negative predictions: {negative}")
            
            # Show first 10 predictions
            print(f"First 10 predictions: {forecast[:10]}")
            
            # Show metrics
            metrics = arima_data['metrics']
            print(f"MAPE: {metrics['MAPE']:.2f}%")
            print(f"RMSE: {metrics['RMSE']:.2f}")
            if 'sMAPE' in metrics:
                print(f"sMAPE: {metrics['sMAPE']:.2f}%")

print("\n\nRECOMMENDATIONS:")
print("1. The extreme MAPE values are likely due to ARIMA producing near-zero or negative predictions")
print("2. This typically happens when ARIMA models fail to capture the pattern properly")
print("3. Consider using:")
print("   - Exponential smoothing models (ETS)")
print("   - Ensure non-negative predictions with transformation")
print("   - Use sMAPE instead of MAPE for evaluation")
print("   - Add minimum prediction constraints")