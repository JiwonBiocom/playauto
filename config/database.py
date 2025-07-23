import os
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st
from contextlib import contextmanager
from typing import Dict, List, Any, Optional

class DatabaseConnection:
    """PostgreSQL database connection manager"""
    
    def __init__(self):
        self.connection_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'playauto'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', '')
        }
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = psycopg2.connect(**self.connection_params)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            st.error(f"Database connection error: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def get_cursor(self, dict_cursor=True):
        """Context manager for database cursor"""
        with self.get_connection() as conn:
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = conn.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """Execute UPDATE/INSERT/DELETE query and return affected rows"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute multiple queries with different parameters"""
        with self.get_cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

# Singleton instance
db = DatabaseConnection()

# Product-related queries
class ProductQueries:
    @staticmethod
    def get_all_products():
        query = """
        SELECT 
            마스터_sku, 플레이오토_sku,
            상품명, 카테고리, 세트유무,
            출고량, 입고량, 현재재고, 
            리드타임, 최소주문수량, 안전재고
        FROM playauto_product_inventory
        ORDER BY 마스터_sku
        """
        return db.execute_query(query)
    
    @staticmethod
    def get_products_by_category(category: str):
        query = """
        SELECT * FROM playauto_product_inventory 
        WHERE 카테고리 = %s
        ORDER BY 마스터_sku
        """
        return db.execute_query(query, (category,))
    
    @staticmethod
    def get_low_stock_products(threshold_ratio: float = 1.0):
        """Get products where current stock is below safety stock * threshold_ratio"""
        query = """
        SELECT * FROM playauto_product_inventory 
        WHERE 현재재고 < (안전재고 * %s)
        ORDER BY (현재재고::float / NULLIF(안전재고, 0)) ASC
        """
        return db.execute_query(query, (threshold_ratio,))
    
    @staticmethod
    def get_product_by_sku(master_sku: str):
        query = """
        SELECT * FROM playauto_product_inventory WHERE 마스터_sku = %s
        """
        results = db.execute_query(query, (master_sku,))
        return results[0] if results else None
    
    @staticmethod
    def update_product(master_sku: str, **kwargs):
        allowed_fields = ['리드타임', '최소주문수량', '안전재고', '현재재고', '출고량', '입고량']
        update_fields = []
        params = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = %s")
                params.append(value)
        
        if not update_fields:
            return 0
        
        params.append(master_sku)
        query = f"""
        UPDATE playauto_product_inventory 
        SET {', '.join(update_fields)}
        WHERE 마스터_sku = %s
        """
        return db.execute_update(query, tuple(params))
    
    @staticmethod
    def process_inventory_in(master_sku: str, quantity: int):
        """Process incoming inventory (increase stock)"""
        query = """
        UPDATE playauto_product_inventory 
        SET 입고량 = 입고량 + %s,
            현재재고 = 현재재고 + %s
        WHERE 마스터_sku = %s
        """
        return db.execute_update(query, (quantity, quantity, master_sku))
    
    @staticmethod
    def process_inventory_out(master_sku: str, quantity: int):
        """Process outgoing inventory (decrease stock)"""
        query = """
        UPDATE playauto_product_inventory 
        SET 출고량 = 출고량 + %s,
            현재재고 = 현재재고 - %s
        WHERE 마스터_sku = %s AND 현재재고 >= %s
        """
        return db.execute_update(query, (quantity, quantity, master_sku, quantity))
    
    @staticmethod
    def adjust_inventory(master_sku: str, new_stock_level: int):
        """Directly adjust inventory to a specific level"""
        query = """
        UPDATE playauto_product_inventory 
        SET 현재재고 = %s
        WHERE 마스터_sku = %s
        """
        return db.execute_update(query, (new_stock_level, master_sku))

# Inventory transaction queries
class InventoryQueries:
    @staticmethod
    def get_inventory_history(product_id: Optional[int] = None, days: int = 30):
        query = """
        SELECT 
            t.transaction_id,
            t.product_id,
            p.product_name,
            t.transaction_type,
            t.quantity,
            t.transaction_date,
            t.created_by,
            t.notes
        FROM inventory_transactions t
        JOIN products p ON t.product_id = p.product_id
        WHERE t.transaction_date >= CURRENT_DATE - INTERVAL '%s days'
        """
        params = [days]
        
        if product_id:
            query += " AND t.product_id = %s"
            params.append(product_id)
        
        query += " ORDER BY t.transaction_date DESC"
        return db.execute_query(query, tuple(params))
    
    @staticmethod
    def add_inventory_transaction(product_id: int, transaction_type: str, 
                                  quantity: int, created_by: str, notes: str = None):
        query = """
        INSERT INTO inventory_transactions 
        (product_id, transaction_type, quantity, created_by, notes)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING transaction_id
        """
        return db.execute_query(query, (product_id, transaction_type, quantity, created_by, notes))
    
    @staticmethod
    def get_daily_sales(product_id: int, days: int = 90):
        query = """
        SELECT 
            DATE(transaction_date) as sale_date,
            SUM(quantity) as total_quantity
        FROM inventory_transactions
        WHERE product_id = %s 
        AND transaction_type = 'OUT'
        AND transaction_date >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY DATE(transaction_date)
        ORDER BY sale_date
        """
        return db.execute_query(query, (product_id, days))

# Prediction queries
class PredictionQueries:
    @staticmethod
    def save_prediction(product_id: int, prediction_date: str, 
                        predicted_quantity: int, model_type: str, confidence: float):
        query = """
        INSERT INTO predictions 
        (product_id, prediction_date, predicted_quantity, model_type, confidence_score)
        VALUES (%s, %s, %s, %s, %s)
        """
        return db.execute_update(query, 
                                 (product_id, prediction_date, predicted_quantity, model_type, confidence))
    
    @staticmethod
    def get_latest_predictions(product_id: Optional[int] = None):
        query = """
        SELECT 
            p.prediction_id,
            p.product_id,
            pr.product_name,
            p.prediction_date,
            p.predicted_quantity,
            p.model_type,
            p.confidence_score,
            p.created_at
        FROM predictions p
        JOIN products pr ON p.product_id = pr.product_id
        WHERE p.created_at = (
            SELECT MAX(created_at) 
            FROM predictions p2 
            WHERE p2.product_id = p.product_id
        )
        """
        if product_id:
            query += " AND p.product_id = %s"
            return db.execute_query(query, (product_id,))
        return db.execute_query(query)