import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

def calculate_safety_stock(predicted_demand: float, lead_time_days: int, 
                          demand_std: float = None, service_level: float = 0.95) -> int:
    """
    Calculate safety stock based on predicted demand and lead time
    
    Args:
        predicted_demand: Predicted daily demand
        lead_time_days: Lead time in days
        demand_std: Standard deviation of demand (optional)
        service_level: Desired service level (default 95%)
    
    Returns:
        Calculated safety stock quantity
    """
    # Basic calculation: predicted_demand * (lead_time_days / 30)
    basic_safety_stock = predicted_demand * (lead_time_days / 30)
    
    # If standard deviation is provided, use more sophisticated calculation
    if demand_std:
        # Z-score for service level (95% = 1.65)
        z_scores = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}
        z_score = z_scores.get(service_level, 1.65)
        
        # Safety stock = Z-score * sqrt(lead_time) * demand_std
        safety_stock = z_score * np.sqrt(lead_time_days) * demand_std
        return max(int(safety_stock), int(basic_safety_stock))
    
    return int(basic_safety_stock)

def calculate_reorder_point(current_stock: int, daily_usage: float, 
                           lead_time_days: int, safety_stock: int) -> Tuple[int, int]:
    """
    Calculate reorder point and days until reorder
    
    Args:
        current_stock: Current inventory level
        daily_usage: Average daily usage
        lead_time_days: Lead time in days
        safety_stock: Safety stock level
    
    Returns:
        Tuple of (reorder_point, days_until_reorder)
    """
    reorder_point = (daily_usage * lead_time_days) + safety_stock
    
    if daily_usage > 0:
        days_until_reorder = max(0, (current_stock - reorder_point) / daily_usage)
    else:
        days_until_reorder = float('inf')
    
    return int(reorder_point), int(days_until_reorder)

def calculate_order_quantity(reorder_point: int, current_stock: int, 
                           moq: int, max_stock: Optional[int] = None) -> int:
    """
    Calculate order quantity considering MOQ and max stock
    
    Args:
        reorder_point: Reorder point level
        current_stock: Current inventory
        moq: Minimum order quantity
        max_stock: Maximum stock level (optional)
    
    Returns:
        Recommended order quantity
    """
    needed_quantity = max(0, reorder_point - current_stock)
    
    # Round up to MOQ
    if moq > 0:
        order_quantity = max(moq, ((needed_quantity // moq) + 1) * moq)
    else:
        order_quantity = needed_quantity
    
    # Check against max stock if provided
    if max_stock:
        max_order = max(0, max_stock - current_stock)
        order_quantity = min(order_quantity, max_order)
    
    return int(order_quantity)

def calculate_stockout_date(current_stock: int, daily_usage: float) -> Optional[datetime]:
    """
    Calculate when stock will run out
    
    Args:
        current_stock: Current inventory level
        daily_usage: Average daily usage
    
    Returns:
        Estimated stockout date or None if usage is 0
    """
    if daily_usage <= 0 or current_stock < 0:
        return None
    
    days_until_stockout = current_stock / daily_usage
    return datetime.now() + timedelta(days=days_until_stockout)

def calculate_inventory_metrics(transactions_df: pd.DataFrame) -> Dict[str, float]:
    """
    Calculate various inventory metrics from transaction history
    
    Args:
        transactions_df: DataFrame with transaction history
    
    Returns:
        Dictionary of calculated metrics
    """
    # Ensure we have the required columns
    if 'quantity' not in transactions_df.columns or 'transaction_type' not in transactions_df.columns:
        return {}
    
    # Calculate metrics
    metrics = {}
    
    # Total in/out
    metrics['total_in'] = transactions_df[transactions_df['transaction_type'] == 'IN']['quantity'].sum()
    metrics['total_out'] = abs(transactions_df[transactions_df['transaction_type'] == 'OUT']['quantity'].sum())
    
    # Average daily usage (last 30 days)
    last_30_days = datetime.now() - timedelta(days=30)
    recent_out = transactions_df[
        (transactions_df['transaction_type'] == 'OUT') & 
        (pd.to_datetime(transactions_df['transaction_date']) >= last_30_days)
    ]
    
    if len(recent_out) > 0:
        days_with_sales = recent_out['transaction_date'].nunique()
        if days_with_sales > 0:
            metrics['avg_daily_usage'] = abs(recent_out['quantity'].sum()) / days_with_sales
        else:
            metrics['avg_daily_usage'] = 0
    else:
        metrics['avg_daily_usage'] = 0
    
    # Inventory turnover ratio
    if metrics.get('total_in', 0) > 0:
        metrics['turnover_ratio'] = metrics['total_out'] / metrics['total_in']
    else:
        metrics['turnover_ratio'] = 0
    
    return metrics

def calculate_prediction_accuracy(actual: List[float], predicted: List[float]) -> Dict[str, float]:
    """
    Calculate prediction accuracy metrics
    
    Args:
        actual: List of actual values
        predicted: List of predicted values
    
    Returns:
        Dictionary of accuracy metrics
    """
    if len(actual) != len(predicted) or len(actual) == 0:
        return {}
    
    actual_arr = np.array(actual)
    predicted_arr = np.array(predicted)
    
    # Remove any NaN values
    mask = ~(np.isnan(actual_arr) | np.isnan(predicted_arr))
    actual_arr = actual_arr[mask]
    predicted_arr = predicted_arr[mask]
    
    if len(actual_arr) == 0:
        return {}
    
    metrics = {}
    
    # Mean Absolute Error
    metrics['mae'] = np.mean(np.abs(actual_arr - predicted_arr))
    
    # Root Mean Square Error
    metrics['rmse'] = np.sqrt(np.mean((actual_arr - predicted_arr) ** 2))
    
    # Mean Absolute Percentage Error
    non_zero_mask = actual_arr != 0
    if np.any(non_zero_mask):
        metrics['mape'] = np.mean(np.abs((actual_arr[non_zero_mask] - predicted_arr[non_zero_mask]) / actual_arr[non_zero_mask])) * 100
    else:
        metrics['mape'] = np.nan
    
    # R-squared
    if len(actual_arr) > 1:
        ss_res = np.sum((actual_arr - predicted_arr) ** 2)
        ss_tot = np.sum((actual_arr - np.mean(actual_arr)) ** 2)
        if ss_tot > 0:
            metrics['r2'] = 1 - (ss_res / ss_tot)
        else:
            metrics['r2'] = 0
    else:
        metrics['r2'] = 0
    
    # Accuracy score (within 10% threshold)
    threshold = 0.1
    within_threshold = np.abs(actual_arr - predicted_arr) <= (actual_arr * threshold)
    metrics['accuracy'] = np.mean(within_threshold) * 100
    
    return metrics

def get_inventory_status(current_stock: int, safety_stock: int, days_until_reorder: int) -> Tuple[str, str]:
    """
    Determine inventory status and urgency level
    
    Args:
        current_stock: Current inventory level
        safety_stock: Safety stock level
        days_until_reorder: Days until reorder needed
    
    Returns:
        Tuple of (status, urgency_level)
    """
    if current_stock <= 0:
        return "재고 없음", "긴급"
    elif current_stock < safety_stock:
        return "재고 부족", "긴급"
    elif days_until_reorder <= 7:
        return "발주 임박", "주의"
    elif days_until_reorder <= 14:
        return "발주 예정", "주의"
    else:
        return "정상", "정상"
