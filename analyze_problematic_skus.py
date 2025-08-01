import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import psycopg2
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
df['시점'] = pd.to_datetime(df['시점'])
df['날짜'] = df['시점'].dt.date

# Aggregate by SKU and date
df_agg = df.groupby(['마스터_SKU', '날짜'])['수량'].sum().reset_index()
df_agg['날짜'] = pd.to_datetime(df_agg['날짜'])

# Problematic SKUs
problematic_skus = ['PROBIO-10B', 'VIT-D-5000', 'LUTEIN-20']
normal_skus = ['CALCIUM-MAG', 'ZINC-15']

print("="*60)
print("ANALYSIS OF PROBLEMATIC SKUs")
print("="*60)

for sku in problematic_skus + normal_skus:
    sku_data = df_agg[df_agg['마스터_SKU'] == sku]['수량'].values
    
    print(f"\n{sku} Statistics:")
    print(f"  Total days: {len(sku_data)}")
    print(f"  Non-zero days: {np.sum(sku_data > 0)}")
    print(f"  Zero days: {np.sum(sku_data == 0)}")
    print(f"  Mean: {np.mean(sku_data):.2f}")
    print(f"  Std: {np.std(sku_data):.2f}")
    print(f"  Min: {np.min(sku_data)}")
    print(f"  Max: {np.max(sku_data)}")
    print(f"  Zero percentage: {(np.sum(sku_data == 0) / len(sku_data) * 100):.1f}%")
    
    # Weekly aggregation analysis
    sku_df = df_agg[df_agg['마스터_SKU'] == sku].copy()
    sku_df['주'] = sku_df['날짜'].dt.to_period('W')
    weekly_agg = sku_df.groupby('주')['수량'].sum().values
    
    print(f"\n  Weekly Statistics:")
    print(f"    Total weeks: {len(weekly_agg)}")
    print(f"    Non-zero weeks: {np.sum(weekly_agg > 0)}")
    print(f"    Zero weeks: {np.sum(weekly_agg == 0)}")
    print(f"    Weekly mean: {np.mean(weekly_agg):.2f}")
    print(f"    Weekly zero percentage: {(np.sum(weekly_agg == 0) / len(weekly_agg) * 100):.1f}%")

# Visualize patterns
fig, axes = plt.subplots(len(problematic_skus), 2, figsize=(15, 5*len(problematic_skus)))

for i, sku in enumerate(problematic_skus):
    sku_df = df_agg[df_agg['마스터_SKU'] == sku].copy()
    sku_df = sku_df.sort_values('날짜')
    
    # Daily data
    axes[i, 0].plot(sku_df['날짜'], sku_df['수량'])
    axes[i, 0].set_title(f'{sku} - Daily Shipments')
    axes[i, 0].set_xlabel('Date')
    axes[i, 0].set_ylabel('Quantity')
    axes[i, 0].grid(True, alpha=0.3)
    
    # Weekly aggregation
    sku_df['주'] = sku_df['날짜'].dt.to_period('W')
    weekly = sku_df.groupby('주')['수량'].sum().reset_index()
    weekly['날짜'] = weekly['주'].apply(lambda x: x.start_time)
    
    axes[i, 1].plot(weekly['날짜'], weekly['수량'])
    axes[i, 1].set_title(f'{sku} - Weekly Shipments')
    axes[i, 1].set_xlabel('Week')
    axes[i, 1].set_ylabel('Quantity')
    axes[i, 1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('problematic_skus_analysis.png')
plt.close()

print("\n\nVisualization saved as 'problematic_skus_analysis.png'")