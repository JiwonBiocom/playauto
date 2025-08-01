import pandas as pd
import numpy as np
import pickle
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, mean_absolute_percentage_error

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

# Aggregate by SKU and date (daily totals)
df_agg = df.groupby(['마스터_SKU', '날짜'])['수량'].sum().reset_index()

# Convert date back to datetime for consistency
df_agg['날짜'] = pd.to_datetime(df_agg['날짜'])

# Create date range to fill missing dates
date_range = pd.date_range(start=df_agg['날짜'].min(), end=df_agg['날짜'].max(), freq='D')

# Process each SKU individually
sku_data = {}
sku_data_weekly = {}

# Configuration
USE_WEEKLY_AGGREGATION = True  # Set to False for daily data

for sku in all_skus:
    # Filter data for this SKU
    sku_df = df_agg[df_agg['마스터_SKU'] == sku].copy()
    
    if len(sku_df) == 0:
        print(f"Warning: No data found for SKU {sku}")
        continue
    
    # Create complete date range
    date_df = pd.DataFrame({'날짜': date_range})
    
    # Merge to fill missing dates
    sku_df = date_df.merge(sku_df, on='날짜', how='left')
    sku_df['마스터_SKU'] = sku
    sku_df['수량'] = sku_df['수량'].fillna(0)
    
    # Sort by date
    sku_df = sku_df.sort_values('날짜')
    
    # Store daily data
    sku_data[sku] = sku_df
    
    # Create weekly aggregation
    if USE_WEEKLY_AGGREGATION:
        sku_df_weekly = sku_df.copy()
        sku_df_weekly['주'] = sku_df_weekly['날짜'].dt.to_period('W')
        weekly_agg = sku_df_weekly.groupby('주')['수량'].sum().reset_index()
        weekly_agg['날짜'] = weekly_agg['주'].apply(lambda x: x.start_time)
        weekly_agg['마스터_SKU'] = sku
        weekly_agg = weekly_agg[['마스터_SKU', '날짜', '수량']]
        sku_data_weekly[sku] = weekly_agg
        
        print(f"Processed {sku}: {len(sku_df)} days → {len(weekly_agg)} weeks, Total: {sku_df['수량'].sum()}")
    else:
        print(f"Processed {sku}: {len(sku_df)} days, Total quantity: {sku_df['수량'].sum()}")

# 3. Train-Test Split Function
def train_test_split_ts(data, test_periods=90, is_weekly=False):
    """Split time series data preserving temporal order"""
    if is_weekly:
        # For weekly data, convert test_days to weeks
        test_weeks = test_periods // 7
        split_date = data['날짜'].max() - pd.Timedelta(weeks=test_weeks)
    else:
        split_date = data['날짜'].max() - pd.Timedelta(days=test_periods)
    
    train = data[data['날짜'] <= split_date].copy()
    test = data[data['날짜'] > split_date].copy()

    return train, test

# 4. ARIMA Model Training
def train_arima(train_data, forecast_days):
    """Train ARIMA model and generate forecasts"""
    try:
        # Prepare data
        y = train_data['수량'].values
        
        # Auto ARIMA would be better, but using manual for now
        model = ARIMA(y, order=(1,1,1))
        model_fit = model.fit()
        
        # Forecast
        forecast = model_fit.forecast(steps=forecast_days)
        
        return forecast, model_fit
    except Exception as e:
        print(f"ARIMA failed: {e}")
        return None, None

# 5. Prophet Model Training
def train_prophet(train_data, forecast_days):
    """Train Prophet model and generate forecasts"""
    try:
        # Prepare data for Prophet
        prophet_data = train_data[['날짜', '수량']].copy()
        prophet_data.columns = ['ds', 'y']
        
        # Initialize and fit model
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model.fit(prophet_data)
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)
        
        # Extract predictions for forecast period
        forecast_values = forecast.iloc[-forecast_days:]['yhat'].values
        
        return forecast_values, model
    except Exception as e:
        print(f"Prophet failed: {e}")
        return None, None

# 6. Model Evaluation
def evaluate_model(actual, predicted):
    """Calculate evaluation metrics"""
    mae = mean_absolute_error(actual, predicted)
    mse = mean_squared_error(actual, predicted)
    rmse = mse ** 0.5
    
    # Custom MAPE calculation to handle zeros
    # Skip zeros in actual values to avoid division by zero
    mask = actual != 0
    if mask.sum() > 0:
        mape = np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100
    else:
        # If all actual values are zero, MAPE is undefined
        mape = np.inf if predicted.sum() > 0 else 0
    
    # Alternative: Symmetric MAPE (sMAPE)
    smape = np.mean(2 * np.abs(actual - predicted) / (np.abs(actual) + np.abs(predicted) + 1e-8)) * 100
    
    return {
        'MAE': mae,
        'RMSE': rmse,
        'MAPE': mape,
        'sMAPE': smape
    }

# 7. Enhanced model training functions for low-data scenarios
def train_arima_enhanced(train_data, forecast_days, min_data_points=30):
    """Train ARIMA with fallback for low data"""
    try:
        y = train_data['수량'].values
        
        # If too little data, use simpler model
        if len(y) < min_data_points:
            # Use simple moving average for very short series
            if len(y) < 7:
                forecast = np.repeat(np.mean(y[-3:]), forecast_days)
                return forecast, None
            # Use simpler ARIMA order
            model = ARIMA(y, order=(0,1,1))
        else:
            # Use SARIMA for seasonal patterns (monthly seasonality)
            # order=(p,d,q), seasonal_order=(P,D,Q,s) where s=4 for weekly or s=30 for daily
            if USE_WEEKLY_AGGREGATION:
                # For weekly data, use 4-week seasonality
                model = ARIMA(y, order=(2,1,2), seasonal_order=(1,1,1,4))
            else:
                # For daily data, use 30-day seasonality (monthly)
                model = ARIMA(y, order=(2,1,2), seasonal_order=(1,1,1,30))
            
        model_fit = model.fit()
        
        # Generate forecasts with prediction intervals
        forecast_result = model_fit.forecast(steps=forecast_days, alpha=0.05)
        
        # Extract point forecasts
        if isinstance(forecast_result, pd.DataFrame):
            forecast = forecast_result.values.flatten()
        else:
            forecast = forecast_result
        
        # Calculate long-term average and recent performance
        long_term_avg = np.mean(y)
        recent_avg = np.mean(y[-30:]) if len(y) > 30 else np.mean(y[-len(y)//2:])
        
        # Detect if recent trend is declining too much
        if len(y) > 60:
            first_half_avg = np.mean(y[:len(y)//2])
            second_half_avg = np.mean(y[len(y)//2:])
            overall_growth_trend = (second_half_avg - first_half_avg) / first_half_avg
        else:
            overall_growth_trend = 0
        
        # Adjust forecasts if they're too pessimistic
        forecast_avg = np.mean(forecast)
        
        # If forecast is much lower than historical average, apply correction
        if forecast_avg < recent_avg * 0.7:  # If forecast is 30% below recent average
            # Blend forecast with recent average
            adjustment_factor = 0.3  # Blend 30% of recent average
            forecast = forecast * (1 - adjustment_factor) + recent_avg * adjustment_factor
        
        # Add monthly variation to avoid flat predictions
        if forecast_days >= 30:
            # Create monthly pattern
            days_per_month = 30
            num_months = forecast_days // days_per_month + 1
            
            # Generate different values for each month
            monthly_factors = []
            for i in range(num_months):
                # Each month gets a slight variation from the base
                month_factor = 1.0 + np.random.uniform(-0.15, 0.15)  # ±15% variation
                monthly_factors.extend([month_factor] * days_per_month)
            
            # Apply monthly factors to forecast
            monthly_factors = np.array(monthly_factors[:forecast_days])
            forecast = forecast * monthly_factors
        
        # If overall historical trend is positive, don't let predictions decline too much
        if overall_growth_trend > 0.1:  # If historical growth > 10%
            # Apply slight upward trend
            growth_rate = min(overall_growth_trend * 0.3, 0.02)  # Cap at 2% per period
            trend_multiplier = 1 + growth_rate * np.arange(forecast_days) / forecast_days
            forecast = forecast * trend_multiplier
        
        # Ensure non-negative forecasts
        forecast = np.maximum(forecast, 0)
        
        return forecast, model_fit
    except Exception as e:
        print(f"ARIMA failed: {e}")
        # Fallback to simple average with monthly variation
        base_forecast = np.mean(train_data['수량'].values[-30:])
        
        # Create monthly variation pattern
        forecast = []
        for i in range(forecast_days):
            month_idx = i // 30
            # Each month gets different variation
            month_variation = 1.0 + (month_idx % 3 - 1) * 0.1  # -10%, 0%, +10%
            daily_value = base_forecast * month_variation * np.random.uniform(0.9, 1.1)
            forecast.append(daily_value)
        
        forecast = np.array(forecast)
        return np.maximum(forecast, 0), None

# 8. Train models for each SKU
forecast_horizons = [30, 60, 90]
model_results = {}
trained_models = {}

# Choose data source based on configuration
data_source = sku_data_weekly if USE_WEEKLY_AGGREGATION else sku_data
forecast_periods = [h//7 if USE_WEEKLY_AGGREGATION else h for h in forecast_horizons]

print(f"\n{'='*60}")
print(f"TRAINING INDIVIDUAL SKU MODELS - {'WEEKLY' if USE_WEEKLY_AGGREGATION else 'DAILY'} DATA")
print(f"{'='*60}")

for sku, data in data_source.items():
    print(f"\n{'='*50}")
    print(f"Training models for SKU: {sku}")
    
    model_results[sku] = {}
    trained_models[sku] = {}
    
    # Check data availability
    non_zero_days = (data['수량'] > 0).sum()
    print(f"Data info: {len(data)} total days, {non_zero_days} days with shipments")
    
    for i, horizon in enumerate(forecast_horizons):
        forecast_period = forecast_periods[i]
        period_label = "weeks" if USE_WEEKLY_AGGREGATION else "days"
        print(f"\nForecast horizon: {horizon} days ({forecast_period} {period_label})")
        
        # Split data
        train, test = train_test_split_ts(data, test_periods=horizon, is_weekly=USE_WEEKLY_AGGREGATION)
        
        # Train ARIMA
        arima_forecast, arima_model = train_arima_enhanced(train, forecast_period)
        
        # Train Prophet
        prophet_forecast, prophet_model = train_prophet(train, forecast_period)
        
        # Store models
        trained_models[sku][horizon] = {
            'arima_model': arima_model,
            'prophet_model': prophet_model
        }
        
        # Evaluate if we have test data
        if len(test) >= forecast_period:
            actual = test.iloc[:forecast_period]['수량'].values
            
            results_horizon = {
                'train_size': len(train),
                'test_size': len(test),
                'non_zero_train': (train['수량'] > 0).sum()
            }
            
            if arima_forecast is not None:
                arima_metrics = evaluate_model(actual[:len(arima_forecast)], arima_forecast)
                results_horizon['arima'] = {
                    'metrics': arima_metrics,
                    'forecast': arima_forecast
                }
                print(f"ARIMA - MAPE: {arima_metrics['MAPE']:.2f}%, RMSE: {arima_metrics['RMSE']:.2f}")
            
            if prophet_forecast is not None:
                prophet_metrics = evaluate_model(actual[:len(prophet_forecast)], prophet_forecast)
                results_horizon['prophet'] = {
                    'metrics': prophet_metrics,
                    'forecast': prophet_forecast
                }
                print(f"Prophet - MAPE: {prophet_metrics['MAPE']:.2f}%, RMSE: {prophet_metrics['RMSE']:.2f}")
            
            model_results[sku][horizon] = results_horizon

# 9. Generate future predictions and determine best model
print(f"\n{'='*50}")
print("Generating future predictions...")

future_predictions = {}
best_models = {}

for sku, data in data_source.items():
    future_predictions[sku] = {}
    best_models[sku] = {}
    
    for i, horizon in enumerate(forecast_horizons):
        forecast_period = forecast_periods[i]
        
        # Determine best model based on evaluation metrics
        if sku in model_results and horizon in model_results[sku]:
            results = model_results[sku][horizon]
            
            # Compare MAPE scores
            arima_mape = results.get('arima', {}).get('metrics', {}).get('MAPE', float('inf'))
            prophet_mape = results.get('prophet', {}).get('metrics', {}).get('MAPE', float('inf'))
            
            best_model = 'arima' if arima_mape < prophet_mape else 'prophet'
            best_models[sku][horizon] = best_model
            
            print(f"\n{sku} - {horizon} days: Best model is {best_model.upper()}")
        else:
            best_models[sku][horizon] = 'arima'  # Default
        
        # Train on all data for final predictions
        arima_forecast, _ = train_arima_enhanced(data, forecast_period)
        prophet_forecast, _ = train_prophet(data, forecast_period)
        
        # Store predictions
        future_predictions[sku][horizon] = {
            'arima': arima_forecast,
            'prophet': prophet_forecast,
            'best_model': best_models[sku][horizon],
            'last_date': data['날짜'].max(),
            'forecast_dates': pd.date_range(
                start=data['날짜'].max() + pd.Timedelta(days=1),
                periods=forecast_period,
                freq='W' if USE_WEEKLY_AGGREGATION else 'D'
            )
        }

# 10. Save models and results
print(f"\n{'='*50}")
print("Saving models and results...")

# Create models directory
import os
os.makedirs('models', exist_ok=True)

# Save trained models
with open('models/trained_models.pkl', 'wb') as f:
    pickle.dump(trained_models, f)

# Save predictions
with open('models/future_predictions.pkl', 'wb') as f:
    pickle.dump(future_predictions, f)

# Save evaluation results
with open('models/model_results.pkl', 'wb') as f:
    pickle.dump(model_results, f)

# Save best model selections
with open('models/best_models.pkl', 'wb') as f:
    pickle.dump(best_models, f)

# Create summary report
summary = []
for sku in all_skus:
    if sku not in model_results:
        continue
    
    sku_summary = {'SKU': sku}
    for horizon in forecast_horizons:
        if horizon in model_results[sku]:
            results = model_results[sku][horizon]
            arima_mape = results.get('arima', {}).get('metrics', {}).get('MAPE', 'N/A')
            prophet_mape = results.get('prophet', {}).get('metrics', {}).get('MAPE', 'N/A')
            best = best_models[sku][horizon]
            
            sku_summary[f'{horizon}d_ARIMA_MAPE'] = arima_mape
            sku_summary[f'{horizon}d_Prophet_MAPE'] = prophet_mape
            sku_summary[f'{horizon}d_Best'] = best
    
    summary.append(sku_summary)

# Save summary as CSV
summary_df = pd.DataFrame(summary)
summary_df.to_csv('models/model_summary.csv', index=False)

print("\nTraining completed!")
print(f"Models saved to 'models/' directory")
print(f"Summary saved to 'models/model_summary.csv'")
