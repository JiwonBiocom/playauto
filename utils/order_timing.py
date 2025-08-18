import numpy as np
from datetime import datetime, timedelta
import pandas as pd


def calculate_reorder_point(current_stock, safety_stock, lead_time, monthly_predictions, moq=1, confidence_level=1.0):  # AI 예측 결과로 발주점(예측 기반 안전재고량)계산
    """
        monthly_predictions: List of 3 monthly predictions [month1, month2, month3]
        moq: Minimum Order Quantity
        confidence_level: Multiplier for safety (1.0 = normal, 1.2 = conservative)
    """
    
    # Calculate average daily consumption from predictions
    if monthly_predictions and len(monthly_predictions) >= 3:
        # Sum of 3-month predictions
        total_3month_forecast = sum(monthly_predictions[:3])
        avg_daily_consumption = total_3month_forecast / 90  # 3 months = ~90 days
    else:
        avg_daily_consumption = 0
    
    # 예측 기반 안전재고량
    proactive_buffer_days = 10  # 10일 전에는 발주 알림이 발생해야 함
    reorder_point = avg_daily_consumption * (lead_time + proactive_buffer_days)
    
    # 재고소진일
    if avg_daily_consumption > 0:
        days_until_safety_stock = (current_stock - safety_stock) / avg_daily_consumption
        days_until_reorder = (current_stock - reorder_point) / avg_daily_consumption
        days_until_stockout = current_stock / avg_daily_consumption
    else:
        days_until_safety_stock = float('inf')
        days_until_reorder = float('inf')
        days_until_stockout = float('inf')
    
    # 상태
    if current_stock <= reorder_point:  # 긴급
        urgency = "긴급"
        order_status = "즉시 발주 필요"
    elif days_until_safety_stock <= 10:  # 주의
        # Alert when 10 days away from safety stock
        urgency = "주의"
        order_status = f"안전재고 도달 {int(days_until_safety_stock)}일 전 - 발주 필요"
    elif days_until_safety_stock <= 20:  # 정상
        urgency = "정상"
        order_status = f"안전재고 도달 {int(days_until_safety_stock)}일 전 - 발주 준비"
    else:  # 정상
        urgency = "정상"
        order_status = ""
    
    # 권장발주량 recommended order quantity
    # Order enough to reach reorder point + lead time demand
    # This ensures we have enough stock to last through the lead time after hitting reorder point
    recommended_qty = reorder_point + (avg_daily_consumption * lead_time) - current_stock
    recommended_qty = max(moq, recommended_qty)  # Ensure at least MOQ
    
    # Round up to MOQ multiples if needed
    if moq > 1 and recommended_qty > moq:
        recommended_qty = ((recommended_qty + moq - 1) // moq) * moq
    
    return {
        'reorder_point': reorder_point,
        'avg_daily_consumption': avg_daily_consumption,  # 일일소비량
        'days_until_safety_stock': days_until_safety_stock,  # 안전재고 도달일
        'days_until_reorder': days_until_reorder,  # 재발주기간
        'days_until_stockout': days_until_stockout,  # 재고소진일
        'order_status': order_status,
        'urgency': urgency,
        'recommended_qty': recommended_qty,  # 권장발주량
        'expected_stockout_date': (datetime.now() + timedelta(days=days_until_stockout)).strftime('%Y-%m-%d') if days_until_stockout != float('inf') else 'N/A'
    }

def calculate_demand_trend(monthly_predictions):
    """
    Calculate demand trend from predictions
    
    Args:
        monthly_predictions: List of monthly predictions
    
    Returns:
        str: Trend indicator (급상승/상승/소폭상승/안정/소폭하락/하락/급하락)
    """
    if not monthly_predictions or len(monthly_predictions) < 2:
        return "데이터 부족"
    
    # Calculate month-over-month changes
    changes = []
    absolute_changes = []
    for i in range(1, len(monthly_predictions)):
        if monthly_predictions[i-1] > 0:
            change_pct = ((monthly_predictions[i] - monthly_predictions[i-1]) / monthly_predictions[i-1]) * 100
            changes.append(change_pct)
            absolute_changes.append(monthly_predictions[i] - monthly_predictions[i-1])
    
    if not changes:
        return "안정 ➡️"
    
    avg_change = np.mean(changes)
    
    # Also check consistency of trend direction
    all_increasing = all(c > 0 for c in changes)
    all_decreasing = all(c < 0 for c in changes)
    
    # More sensitive thresholds with multiple levels
    if avg_change > 15 or (avg_change > 10 and all_increasing):
        return "급상승 ⬆️"
    elif avg_change > 7:
        return "상승 📈"
    elif avg_change > 3:
        return "소폭상승 ↗️"
    elif avg_change < -15 or (avg_change < -10 and all_decreasing):
        return "급하락 ⬇️"
    elif avg_change < -7:
        return "하락 📉"
    elif avg_change < -3:
        return "소폭하락 ↘️"
    else:
        # Only mark as stable if change is really minimal (within ±3%)
        return "안정 ➡️"

def get_order_priority(urgency, current_stock, safety_stock, days_until_stockout):
    """
    Calculate order priority score (1-10)
    
    Args:
        urgency: Order urgency status
        current_stock: Current inventory
        safety_stock: Safety stock level
        days_until_stockout: Days until stockout
    
    Returns:
        int: Priority score (10 = highest priority)
    """
    score = 5  # Base score
    
    # Urgency factor
    if urgency == "긴급":
        score += 3
    elif urgency == "주의":
        score += 1
    
    # Stock level factor
    if current_stock < safety_stock * 0.5:
        score += 2
    elif current_stock < safety_stock:
        score += 1
    
    # Days until stockout factor
    if days_until_stockout < 7:
        score += 2
    elif days_until_stockout < 14:
        score += 1
    
    return min(10, max(1, score))

def batch_calculate_reorder_points(products_df, predictions_dict, confidence_level=1.0):
    """
    Calculate reorder points for multiple products
    
    Args:
        products_df: DataFrame with product information
        predictions_dict: Dictionary of predictions by SKU
        confidence_level: Safety multiplier
    
    Returns:
        DataFrame with reorder calculations
    """
    results = []
    
    for _, product in products_df.iterrows():
        sku = product.get('마스터_sku', '')
        
        # Get predictions for this SKU
        if sku in predictions_dict:
            pred_data = predictions_dict[sku]
            
            # Extract monthly predictions based on model structure
            if 'arima' in pred_data and isinstance(pred_data['arima'], (list, np.ndarray)):
                monthly_predictions = list(pred_data['arima'][:3])
            elif 'forecast_months' in pred_data:
                # Adaptive model structure
                if 'adaptive_forecast' in pred_data:
                    monthly_predictions = list(pred_data['adaptive_forecast'][:3])
                else:
                    monthly_predictions = list(pred_data.get('arima', [])[:3])
            else:
                monthly_predictions = []
        else:
            monthly_predictions = []
        
        # Calculate reorder point
        reorder_info = calculate_reorder_point(
            current_stock=product.get('현재재고', 0),
            safety_stock=product.get('안전재고', 0),
            lead_time=product.get('리드타임', 7),
            monthly_predictions=monthly_predictions,
            confidence_level=confidence_level
        )
        
        # Add product info
        reorder_info['마스터_sku'] = sku
        reorder_info['상품명'] = product.get('상품명', '')
        reorder_info['현재재고'] = product.get('현재재고', 0)
        reorder_info['안전재고'] = product.get('안전재고', 0)
        reorder_info['리드타임'] = product.get('리드타임', 7)
        reorder_info['MOQ'] = product.get('최소주문수량', 1)
        reorder_info['demand_trend'] = calculate_demand_trend(monthly_predictions)
        reorder_info['priority'] = get_order_priority(
            reorder_info['urgency'],
            product.get('현재재고', 0),
            product.get('안전재고', 0),
            reorder_info['days_until_stockout']
        )
        
        # Adjust recommended quantity to MOQ
        moq = product.get('최소주문수량', 1)
        if moq > 1:
            reorder_info['recommended_qty'] = ((reorder_info['recommended_qty'] + moq - 1) // moq) * moq
        
        results.append(reorder_info)
    
    return pd.DataFrame(results)
