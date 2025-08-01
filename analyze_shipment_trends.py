import pandas as pd
import numpy as np
import pickle
import matplotlib.pyplot as plt
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

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
df['시점'] = pd.to_datetime(df['시점'])

# Analyze monthly trends
df['year_month'] = df['시점'].dt.to_period('M')
monthly_shipments = df.groupby(['마스터_SKU', 'year_month'])['수량'].agg(['sum', 'count', 'mean']).reset_index()

print("="*60)
print("MONTHLY SHIPMENT ANALYSIS")
print("="*60)

for sku in df['마스터_SKU'].unique():
    sku_data = monthly_shipments[monthly_shipments['마스터_SKU'] == sku].sort_values('year_month')
    
    if len(sku_data) < 3:
        continue
        
    print(f"\n{sku}:")
    print("-"*40)
    
    # Calculate month-over-month growth
    sku_data['growth_rate'] = sku_data['sum'].pct_change()
    
    # Show recent trends
    recent_months = sku_data.tail(6)
    for _, row in recent_months.iterrows():
        growth_str = f"{row['growth_rate']*100:.1f}%" if pd.notna(row['growth_rate']) else "N/A"
        print(f"{row['year_month']}: Total={row['sum']:.0f}, Count={row['count']}, Avg={row['mean']:.1f}, Growth={growth_str}")
    
    # Calculate average growth rate
    avg_growth = sku_data['growth_rate'].mean()
    recent_avg_growth = sku_data.tail(3)['growth_rate'].mean()
    
    print(f"\nAverage monthly growth: {avg_growth*100:.1f}%")
    print(f"Recent 3-month growth: {recent_avg_growth*100:.1f}%")
    
    # Check for trend
    if len(sku_data) >= 4:
        # Simple linear trend on recent data
        x = np.arange(len(sku_data.tail(4)))
        y = sku_data.tail(4)['sum'].values
        if len(y) > 0 and np.std(y) > 0:
            trend = np.polyfit(x, y, 1)[0]
            print(f"Recent trend (slope): {trend:.2f} units/month")

print("\n\nKEY INSIGHTS:")
print("1. Look for positive growth rates - if historical data shows growth, predictions should too")
print("2. Check if there's seasonality in the monthly patterns")
print("3. Recent trends are more important than overall average")

# Save the monthly analysis
monthly_shipments.to_csv('monthly_shipments_analysis.csv', index=False)
print("\nMonthly analysis saved to 'monthly_shipments_analysis.csv'")