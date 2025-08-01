import pickle
import pandas as pd

# Load predictions
with open('models/future_predictions.pkl', 'rb') as f:
    future_predictions = pickle.load(f)

print("Available SKUs with predictions:")
print("="*50)

for sku in sorted(future_predictions.keys()):
    print(f"\n{sku}:")
    for horizon in sorted(future_predictions[sku].keys()):
        pred_data = future_predictions[sku][horizon]
        if 'arima' in pred_data and len(pred_data['arima']) > 0:
            print(f"  {horizon} days: {len(pred_data['arima'])} predictions available")
        else:
            print(f"  {horizon} days: No predictions")

print("\n\nProduct name mapping needed:")
print("="*50)

# SKUs that need product names
skus_with_predictions = list(future_predictions.keys())
print("SKUs with predictions:", skus_with_predictions)

# Current mapping in app.py
current_mapping = {
    '비타민C 1000mg': 'VIT-C-1000',
    '오메가3 500mg': 'OMEGA-3-500',
    '프로바이오틱스 10B': 'PROBIO-10B',
    '비타민D 5000IU': 'VIT-D-5000',
    '종합비타민': 'MULTI-VIT',
    '칼슘&마그네슘': 'CALCIUM-MAG',
    '철분 18mg': 'IRON-18',
    '아연 15mg': 'ZINC-15',
    '콜라겐 1000mg': 'COLLAGEN-1K',
    '루테인 20mg': 'LUTEIN-20'
}

print("\nSKUs without predictions:")
for product_name, sku in current_mapping.items():
    if sku not in skus_with_predictions:
        print(f"  {product_name} ({sku}) - NO PREDICTIONS")
    else:
        print(f"  {product_name} ({sku}) - OK")