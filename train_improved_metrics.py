import pandas as pd
import numpy as np
import pickle
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# PostgreSQL connection
conn_ps = psycopg2.connect(
    host="15.164.112.237", 
    database="dify", 
    user="difyuser", 
    password="bico0218"
)

conn_ps.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cursor_ps = conn_ps.cursor()

query = """
    SELECT 마스터_SKU, 수량, 시점
    FROM playauto_shipment_receipt
    WHERE 입출고_여부 = '출고'
    ORDER BY 마스터_SKU, 시점
"""
cursor_ps.execute(query)
result = cursor_ps.fetchall()

df = pd.DataFrame(result, columns=['마스터_SKU', '수량', '시점'])

# Process data
df['시점'] = pd.to_datetime(df['시점'])
df['날짜'] = df['시점'].dt.date
df['연월'] = df['시점'].dt.to_period('M')

# Aggregate by SKU and month
df_monthly = df.groupby(['마스터_SKU', '연월'])['수량'].sum().reset_index()
df_monthly['날짜'] = df_monthly['연월'].dt.to_timestamp()

# List of all SKUs
all_skus = ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B', 'VIT-D-5000', 'CALCIUM-MAG', 'ZINC-15', 
            'COLLAGEN-1K', 'LUTEIN-20', 'IRON-18', 'MULTI-VIT']

# Process each SKU
sku_data_monthly = {}
for sku in all_skus:
    sku_df = df_monthly[df_monthly['마스터_SKU'] == sku].copy()
    if len(sku_df) > 0:
        sku_df = sku_df.sort_values('날짜')
        sku_data_monthly[sku] = sku_df
        print(f"Processed {sku}: {len(sku_df)} months, Total quantity: {sku_df['수량'].sum()}")

# Enhanced ARIMA with seasonal components
def train_arima_seasonal(train_data, forecast_months, sku_name):
    """Train ARIMA model with seasonal components"""
    try:
        y = train_data['수량'].values
        
        if len(y) < 4:
            base_avg = np.mean(y)
            growth_rate = 0.05
            forecast = []
            for i in range(forecast_months):
                forecast.append(base_avg * (1 + growth_rate * i))
            return np.array(forecast), None
        
        # Determine model parameters based on SKU
        if sku_name == 'VIT-C-1000' and len(y) >= 6:
            model = ARIMA(y, order=(2,1,1), seasonal_order=(1,0,1,6))
        else:
            model = ARIMA(y, order=(1,1,1))
        
        model_fit = model.fit()
        forecast = model_fit.forecast(steps=forecast_months)
        
        # Apply seasonal adjustments for VIT-C-1000
        if sku_name == 'VIT-C-1000':
            last_month = train_data['연월'].iloc[-1].month
            seasonal_factors = {
                1: 0.9, 2: 1.0, 3: 1.6, 4: 1.4, 5: 1.2, 6: 1.4, 7: 1.8,
                8: 1.7, 9: 1.6, 10: 1.5, 11: 1.4, 12: 1.3
            }
            
            adjusted_forecast = []
            for i in range(forecast_months):
                future_month = ((last_month + i) % 12) + 1
                seasonal_factor = seasonal_factors.get(future_month, 1.0)
                base_forecast = forecast[i] if isinstance(forecast, np.ndarray) else forecast.iloc[i]
                adjusted_value = base_forecast * 0.7 + (np.mean(y) * seasonal_factor) * 0.3
                adjusted_forecast.append(max(adjusted_value, 0))
            
            forecast = np.array(adjusted_forecast)
        
        forecast = np.maximum(forecast, 0)
        return forecast, model_fit
        
    except Exception as e:
        print(f"ARIMA failed for {sku_name}: {e}")
        if len(train_data) >= 3:
            recent_avg = train_data['수량'].iloc[-3:].mean()
        else:
            recent_avg = train_data['수량'].mean()
        
        forecast = []
        for i in range(forecast_months):
            if sku_name == 'VIT-C-1000':
                month_multiplier = [1.1, 1.05, 1.0][i] if i < 3 else 1.0
            else:
                month_multiplier = 1.0
            forecast.append(recent_avg * month_multiplier)
        
        return np.array(forecast), None

# Calculate metrics using cross-validation
def calculate_cv_metrics(data, sku_name, n_splits=3):
    """Calculate metrics using time series cross-validation"""
    if len(data) < 4:
        return None
    
    # Use TimeSeriesSplit for cross-validation
    tscv = TimeSeriesSplit(n_splits=min(n_splits, len(data) - 2))
    
    errors = []
    
    for train_idx, test_idx in tscv.split(data):
        train = data.iloc[train_idx]
        test = data.iloc[test_idx]
        
        if len(test) == 0:
            continue
        
        # Make predictions
        forecast, _ = train_arima_seasonal(train, len(test), sku_name)
        
        if forecast is not None and len(forecast) > 0:
            actual = test['수량'].values
            predicted = forecast[:len(actual)]
            
            # Calculate errors
            mae = mean_absolute_error(actual, predicted)
            mse = mean_squared_error(actual, predicted)
            
            # MAPE calculation
            mask = actual != 0
            if mask.sum() > 0:
                mape = np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100
            else:
                mape = np.inf if predicted.sum() > 0 else 0
            
            errors.append({
                'MAE': mae,
                'RMSE': np.sqrt(mse),
                'MAPE': mape
            })
    
    if len(errors) == 0:
        return None
    
    # Average metrics across folds
    avg_metrics = {
        'MAE': np.mean([e['MAE'] for e in errors]),
        'RMSE': np.mean([e['RMSE'] for e in errors]),
        'MAPE': np.mean([e['MAPE'] for e in errors if e['MAPE'] < np.inf])
    }
    
    return avg_metrics

# Train models and calculate metrics
model_results = {}
trained_models = {}
future_predictions = {}

print(f"\n{'='*60}")
print(f"TRAINING MODELS WITH CROSS-VALIDATION METRICS")
print(f"{'='*60}")

for sku, data in sku_data_monthly.items():
    print(f"\n{'='*50}")
    print(f"Training models for SKU: {sku}")
    
    # Calculate cross-validation metrics
    cv_metrics = calculate_cv_metrics(data, sku)
    
    if cv_metrics:
        print(f"Cross-validation metrics:")
        print(f"  RMSE: {cv_metrics['RMSE']:.2f}")
        print(f"  MAE: {cv_metrics['MAE']:.2f}")
        print(f"  MAPE: {cv_metrics['MAPE']:.2f}%")
        
        # Store metrics
        model_results[sku] = {
            'arima': {
                'metrics': cv_metrics,
                'train_size': len(data),
                'cv_folds': 3
            }
        }
    else:
        print(f"  Insufficient data for cross-validation")
        model_results[sku] = {}
    
    # Train final model on all data
    forecast_months = 3
    final_arima_forecast, arima_model = train_arima_seasonal(data, forecast_months, sku)
    
    # Store models and predictions
    trained_models[sku] = {
        'arima_model': arima_model,
        'prophet_model': None
    }
    
    future_predictions[sku] = {
        'arima': final_arima_forecast,
        'prophet': None,
        'best_model': 'arima',
        'last_date': data['날짜'].max(),
        'forecast_months': ['August 2025', 'September 2025', 'October 2025']
    }
    
    print(f"Final predictions: {final_arima_forecast}")

# Special report for VIT-C-1000
print(f"\n{'='*60}")
print("DETAILED ANALYSIS FOR VIT-C-1000")
print(f"{'='*60}")

if 'VIT-C-1000' in sku_data_monthly:
    vitc_data = sku_data_monthly['VIT-C-1000']
    print("\nHistorical monthly totals:")
    for _, row in vitc_data.iterrows():
        print(f"{row['연월']}: {row['수량']} units")
    
    vitc_predictions = future_predictions['VIT-C-1000']
    print(f"\nPredictions for Aug-Oct 2025:")
    print(f"ARIMA: {vitc_predictions['arima']}")
    
    if 'VIT-C-1000' in model_results and model_results['VIT-C-1000']:
        metrics = model_results['VIT-C-1000']['arima']['metrics']
        print(f"\nModel accuracy (cross-validation):")
        print(f"  RMSE: {metrics['RMSE']:.2f}")
        print(f"  MAPE: {metrics['MAPE']:.2f}%")

# Save everything
import os
os.makedirs('models_improved', exist_ok=True)

with open('models_improved/trained_models.pkl', 'wb') as f:
    pickle.dump(trained_models, f)

with open('models_improved/future_predictions.pkl', 'wb') as f:
    pickle.dump(future_predictions, f)

with open('models_improved/model_results.pkl', 'wb') as f:
    pickle.dump(model_results, f)

# Create summary report
summary_data = []
for sku in all_skus:
    if sku in model_results and model_results[sku]:
        metrics = model_results[sku]['arima']['metrics']
        predictions = future_predictions[sku]['arima']
        
        summary_data.append({
            'SKU': sku,
            'RMSE': metrics['RMSE'],
            'MAPE': metrics['MAPE'],
            'Aug_Prediction': predictions[0],
            'Sep_Prediction': predictions[1],
            'Oct_Prediction': predictions[2],
            'Total_Q3': predictions.sum()
        })

if summary_data:
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv('models_improved/model_summary_with_metrics.csv', index=False)

print("\nTraining completed with metrics!")
print(f"Models saved to 'models_improved/' directory")

# Close database connection
conn_ps.close()