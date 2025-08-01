import pandas as pd
import numpy as np
import pickle
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, mean_absolute_percentage_error
from statsmodels.tsa.stattools import adfuller
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
import matplotlib.pyplot as plt

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


# PostgreSQL과 연동
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

# List of all SKUs
all_skus = ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B', 'VIT-D-5000', 'CALCIUM-MAG', 'ZINC-15', 
            'COLLAGEN-1K', 'LUTEIN-20', 'ENZYME', 'IRON-18', 'MULTI-VIT', 'ADRENALYZE']

# 1. Data Preprocessing
# Convert 시점 to datetime
df['시점'] = pd.to_datetime(df['시점'])

# Extract date only (remove time component)
df['날짜'] = df['시점'].dt.date

# Create monthly aggregation for better seasonality capture
df['연월'] = df['시점'].dt.to_period('M')

# Aggregate by SKU and month (monthly totals)
df_monthly = df.groupby(['마스터_SKU', '연월'])['수량'].sum().reset_index()

# Convert period to timestamp for modeling
df_monthly['날짜'] = df_monthly['연월'].dt.to_timestamp()

# Process each SKU individually
sku_data_monthly = {}

for sku in all_skus:
    # Filter data for this SKU
    sku_df = df_monthly[df_monthly['마스터_SKU'] == sku].copy()
    
    if len(sku_df) == 0:
        print(f"Warning: No data found for SKU {sku}")
        continue
    
    # Sort by date
    sku_df = sku_df.sort_values('날짜')
    
    # Store monthly data
    sku_data_monthly[sku] = sku_df
    
    print(f"Processed {sku}: {len(sku_df)} months, Total quantity: {sku_df['수량'].sum()}")

# 3. Train-Test Split Function
def train_test_split_ts(data, test_months=3):
    """Split time series data preserving temporal order"""
    if len(data) <= test_months:
        return data, pd.DataFrame()
    
    train = data[:-test_months].copy()
    test = data[-test_months:].copy()
    
    return train, test

# 4. Enhanced ARIMA Model Training with proper seasonal handling
def train_arima_seasonal(train_data, forecast_months, sku_name):
    """Train ARIMA model with seasonal components"""
    try:
        # Prepare data
        y = train_data['수량'].values
        
        # For very short series, use simple forecast
        if len(y) < 4:
            # Use average with growth trend
            base_avg = np.mean(y)
            growth_rate = 0.05  # 5% monthly growth
            forecast = []
            for i in range(forecast_months):
                forecast.append(base_avg * (1 + growth_rate * i))
            return np.array(forecast), None
        
        # Check for stationarity
        adf_result = adfuller(y)
        d = 0 if adf_result[1] < 0.05 else 1
        
        # Determine seasonal pattern based on SKU characteristics
        # VIT-C-1000 shows clear seasonal pattern
        if sku_name == 'VIT-C-1000':
            # Based on the data pattern: low in Feb, peak in Mar/Jul
            # Use SARIMA with monthly seasonality
            if len(y) >= 6:
                # SARIMA model: (p,d,q)(P,D,Q)s
                # s=6 for semi-annual pattern
                model = ARIMA(y, order=(2,d,1), seasonal_order=(1,0,1,6))
            else:
                model = ARIMA(y, order=(1,d,1))
        else:
            # For other SKUs, use auto-determined parameters
            if len(y) >= 12:
                model = ARIMA(y, order=(2,d,2), seasonal_order=(1,0,1,12))
            else:
                model = ARIMA(y, order=(1,d,1))
        
        model_fit = model.fit()
        
        # Generate forecasts
        forecast = model_fit.forecast(steps=forecast_months)
        
        # Apply seasonal adjustments for VIT-C-1000
        if sku_name == 'VIT-C-1000':
            # Based on historical pattern:
            # Feb: low (base), Mar: +60%, Apr: +40%, May: +20%, Jun: +40%, Jul: +80%
            # Aug-Oct should follow summer/fall pattern
            last_month = train_data['연월'].iloc[-1].month
            seasonal_factors = {
                1: 0.9,   # Jan
                2: 1.0,   # Feb (base)
                3: 1.6,   # Mar
                4: 1.4,   # Apr
                5: 1.2,   # May
                6: 1.4,   # Jun
                7: 1.8,   # Jul
                8: 1.7,   # Aug (maintain high summer demand)
                9: 1.6,   # Sep (slight decrease)
                10: 1.5,  # Oct (autumn immunity boost)
                11: 1.4,  # Nov
                12: 1.3   # Dec
            }
            
            # Apply seasonal adjustment
            adjusted_forecast = []
            for i in range(forecast_months):
                future_month = ((last_month + i) % 12) + 1
                seasonal_factor = seasonal_factors.get(future_month, 1.0)
                
                # Blend model forecast with seasonal adjustment
                base_forecast = forecast[i] if isinstance(forecast, np.ndarray) else forecast.iloc[i]
                adjusted_value = base_forecast * 0.7 + (np.mean(y) * seasonal_factor) * 0.3
                adjusted_forecast.append(max(adjusted_value, 0))
            
            forecast = np.array(adjusted_forecast)
        
        # Ensure non-negative forecasts
        forecast = np.maximum(forecast, 0)
        
        return forecast, model_fit
        
    except Exception as e:
        print(f"ARIMA failed for {sku_name}: {e}")
        # Fallback to seasonal average
        if len(train_data) >= 3:
            recent_avg = train_data['수량'].iloc[-3:].mean()
        else:
            recent_avg = train_data['수량'].mean()
        
        # Apply growth trend
        forecast = []
        for i in range(forecast_months):
            if sku_name == 'VIT-C-1000':
                # For VIT-C-1000, ensure August-October predictions are reasonable
                month_multiplier = [1.1, 1.05, 1.0][i] if i < 3 else 1.0
            else:
                month_multiplier = 1.0
            forecast.append(recent_avg * month_multiplier)
        
        return np.array(forecast), None

# 5. Prophet Model Training (keep existing)
def train_prophet(train_data, forecast_months):
    """Train Prophet model and generate forecasts"""
    try:
        # Prepare data for Prophet
        prophet_data = train_data[['날짜', '수량']].copy()
        prophet_data.columns = ['ds', 'y']
        
        # Initialize and fit model
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.1,
            seasonality_prior_scale=10.0
        )
        model.fit(prophet_data)
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=forecast_months, freq='MS')
        forecast = model.predict(future)
        
        # Extract predictions for forecast period
        forecast_values = forecast.iloc[-forecast_months:]['yhat'].values
        
        return forecast_values, model
    except Exception as e:
        print(f"Prophet failed: {e}")
        return None, None

# 6. Model Evaluation (keep existing)
def evaluate_model(actual, predicted):
    """Calculate evaluation metrics"""
    mae = mean_absolute_error(actual, predicted)
    mse = mean_squared_error(actual, predicted)
    rmse = mse ** 0.5
    
    # Custom MAPE calculation to handle zeros
    mask = actual != 0
    if mask.sum() > 0:
        mape = np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100
    else:
        mape = np.inf if predicted.sum() > 0 else 0
    
    # Symmetric MAPE
    smape = np.mean(2 * np.abs(actual - predicted) / (np.abs(actual) + np.abs(predicted) + 1e-8)) * 100
    
    return {
        'MAE': mae,
        'RMSE': rmse,
        'MAPE': mape,
        'sMAPE': smape
    }

# 7. Train models for each SKU
model_results = {}
trained_models = {}
future_predictions = {}

print(f"\n{'='*60}")
print(f"TRAINING IMPROVED MODELS WITH MONTHLY SEASONALITY")
print(f"{'='*60}")

for sku, data in sku_data_monthly.items():
    print(f"\n{'='*50}")
    print(f"Training models for SKU: {sku}")
    
    model_results[sku] = {}
    trained_models[sku] = {}
    future_predictions[sku] = {}
    
    # Check data availability
    print(f"Data info: {len(data)} months available")
    
    # For monthly data, we'll predict 3 months ahead
    forecast_months = 3
    
    # Split data (keep last 3 months for testing if we have enough data)
    if len(data) > 6:
        train, test = train_test_split_ts(data, test_months=3)
    else:
        train = data
        test = pd.DataFrame()
    
    # Train ARIMA with seasonal components
    arima_forecast, arima_model = train_arima_seasonal(train, forecast_months, sku)
    
    # Train Prophet
    prophet_forecast, prophet_model = train_prophet(train, forecast_months)
    
    # Store models
    trained_models[sku] = {
        'arima_model': arima_model,
        'prophet_model': prophet_model
    }
    
    # Evaluate if we have test data
    if len(test) > 0:
        actual = test['수량'].values
        
        results = {
            'train_size': len(train),
            'test_size': len(test)
        }
        
        if arima_forecast is not None:
            arima_metrics = evaluate_model(actual[:len(arima_forecast)], arima_forecast[:len(actual)])
            results['arima'] = {
                'metrics': arima_metrics,
                'forecast': arima_forecast
            }
            print(f"ARIMA - MAPE: {arima_metrics['MAPE']:.2f}%, RMSE: {arima_metrics['RMSE']:.2f}")
        
        if prophet_forecast is not None:
            prophet_metrics = evaluate_model(actual[:len(prophet_forecast)], prophet_forecast[:len(actual)])
            results['prophet'] = {
                'metrics': prophet_metrics,
                'forecast': prophet_forecast
            }
            print(f"Prophet - MAPE: {prophet_metrics['MAPE']:.2f}%, RMSE: {prophet_metrics['RMSE']:.2f}")
        
        model_results[sku] = results
    
    # Generate future predictions using all data
    print(f"\nGenerating future predictions for {sku}...")
    
    # Train on all data
    final_arima_forecast, _ = train_arima_seasonal(data, forecast_months, sku)
    final_prophet_forecast, _ = train_prophet(data, forecast_months)
    
    # Determine best model
    if sku in model_results and 'arima' in model_results[sku] and 'prophet' in model_results[sku]:
        arima_mape = model_results[sku]['arima']['metrics']['MAPE']
        prophet_mape = model_results[sku]['prophet']['metrics']['MAPE']
        best_model = 'arima' if arima_mape < prophet_mape else 'prophet'
    else:
        best_model = 'arima'  # Default
    
    # Store predictions
    future_predictions[sku] = {
        'arima': final_arima_forecast,
        'prophet': final_prophet_forecast,
        'best_model': best_model,
        'last_date': data['날짜'].max(),
        'forecast_months': ['August 2025', 'September 2025', 'October 2025']
    }
    
    print(f"Best model: {best_model.upper()}")
    print(f"ARIMA predictions: {final_arima_forecast}")
    if final_prophet_forecast is not None:
        print(f"Prophet predictions: {final_prophet_forecast}")

# 8. Special focus on VIT-C-1000
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
    if vitc_predictions['prophet'] is not None:
        print(f"Prophet: {vitc_predictions['prophet']}")
    
    # Calculate daily average predictions
    print(f"\nDaily average predictions (assuming 30 days/month):")
    for i, month in enumerate(['August', 'September', 'October']):
        arima_daily = vitc_predictions['arima'][i] / 30
        print(f"{month}: {arima_daily:.1f} units/day")

# 9. Save improved models and results
print(f"\n{'='*50}")
print("Saving improved models and results...")

# Create models directory
import os
os.makedirs('models_improved', exist_ok=True)

# Save trained models
with open('models_improved/trained_models.pkl', 'wb') as f:
    pickle.dump(trained_models, f)

# Save predictions
with open('models_improved/future_predictions.pkl', 'wb') as f:
    pickle.dump(future_predictions, f)

# Save evaluation results
with open('models_improved/model_results.pkl', 'wb') as f:
    pickle.dump(model_results, f)

# Create detailed report for VIT-C-1000
if 'VIT-C-1000' in future_predictions:
    vitc_report = {
        'SKU': 'VIT-C-1000',
        'Historical_Avg': sku_data_monthly['VIT-C-1000']['수량'].mean(),
        'Last_Month_Value': sku_data_monthly['VIT-C-1000']['수량'].iloc[-1],
        'Aug_Prediction': future_predictions['VIT-C-1000']['arima'][0],
        'Sep_Prediction': future_predictions['VIT-C-1000']['arima'][1],
        'Oct_Prediction': future_predictions['VIT-C-1000']['arima'][2],
        'Total_Q3_Prediction': future_predictions['VIT-C-1000']['arima'].sum(),
        'Best_Model': future_predictions['VIT-C-1000']['best_model']
    }
    
    report_df = pd.DataFrame([vitc_report])
    report_df.to_csv('models_improved/vitc_prediction_report.csv', index=False)

print("\nImproved training completed!")
print(f"Models saved to 'models_improved/' directory")
print(f"VIT-C-1000 report saved to 'models_improved/vitc_prediction_report.csv'")

# Close database connection
conn_ps.close()