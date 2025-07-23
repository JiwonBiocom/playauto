import os
from datetime import timedelta

# Application settings
APP_NAME = "PLAYAUTO"
APP_VERSION = "1.0.0"

# Model settings
PREDICTION_MODELS = {
    'prophet': 'Prophet (권장)',
    'arima': 'ARIMA',
    'lstm': 'LSTM'
}

DEFAULT_MODEL = os.getenv('DEFAULT_PREDICTION_MODEL', 'prophet')

# Prediction periods
PREDICTION_PERIODS = {
    '30일': 30,
    '60일': 60,
    '90일': 90
}

# Alert settings
ALERT_TYPES = {
    'stock_shortage': '재고 부족',
    'order_point': '발주 시점',
    'expiry_warning': '소비기한 임박',
    'overstock': '과잉 재고'
}

DEFAULT_ALERT_SETTINGS = {
    'stock_shortage_days': 10,
    'order_alert_days': 10,
    'expiry_alert_days': 30,
    'overstock_ratio': 200
}

# Safety stock calculation
SAFETY_STOCK_MULTIPLIER = 1.5  # Safety factor for stock calculation

# File upload settings
ALLOWED_FILE_TYPES = ['csv', 'xlsx', 'xls']
MAX_FILE_SIZE_MB = 10

# Pagination
DEFAULT_PAGE_SIZE = 20

# Date formats
DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# Categories
PRODUCT_CATEGORIES = [
    '비타민',
    '오메가3',
    '프로바이오틱스',
    '건강식품',
    '기타'
]

# Suppliers
SUPPLIERS = {
    1: 'NPK',
    2: '다빈치랩',
    3: '바이오땡'
}

# Default supplier lead times (days)
DEFAULT_LEAD_TIMES = {
    'NPK': 120,
    '다빈치랩': 30,
    '바이오땡': 45
}

# Transaction types
TRANSACTION_TYPES = {
    'IN': '입고',
    'OUT': '출고',
    'ADJUST': '재고조정'
}

# Status colors for Streamlit
STATUS_COLORS = {
    '정상': '#28a745',
    '주의': '#ffc107',
    '긴급': '#dc3545',
    '경고': '#fd7e14'
}

# Chart settings
CHART_HEIGHT = 400
CHART_COLOR_SCHEME = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']

# Model performance metrics
PERFORMANCE_METRICS = ['RMSE', 'MAE', 'MAPE', 'R2']

# Excel template columns
TEMPLATE_COLUMNS = [
    '마스터 SKU',
    '플레이오토 SKU',
    '상품명',
    '카테고리',
    '세트 유무',
    '현재 재고',
    '입고량',
    '출고량'
]