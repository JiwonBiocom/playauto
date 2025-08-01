import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection parameters
conn_params = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'playauto'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

# Sample data for 10 products
sample_data = [
    # (마스터_SKU, 플레이오토_SKU, 상품명, 카테고리, 세트유무, 출고량, 입고량, 현재재고, 리드타임, 최소주문수량, 안전재고)
    ('VIT-C-1000', 'PA-001', '비타민C 1000mg', '비타민', '단품', 1500, 2000, 150, 30, 100, 100),
    ('OMEGA-3-500', 'PA-002', '오메가3 500mg', '오메가3', '단품', 2000, 1500, 45, 45, 50, 100),
    ('PROBIO-10B', 'PA-003', '프로바이오틱스 10B', '프로바이오틱스', '단품', 1000, 1500, 200, 15, 30, 150),
    ('VIT-D-5000', 'PA-004', '비타민D 5000IU', '비타민', '단품', 800, 1000, 180, 30, 50, 120),
    ('MULTI-VIT', 'PA-005', '종합비타민', '비타민', '세트', 1200, 1800, 300, 60, 100, 200),
    ('CALCIUM-MAG', 'PA-006', '칼슘&마그네슘', '건강식품', '세트', 600, 800, 120, 40, 50, 80),
    ('IRON-18', 'PA-007', '철분 18mg', '건강식품', '단품', 400, 500, 80, 35, 30, 60),
    ('ZINC-15', 'PA-008', '아연 15mg', '건강식품', '단품', 500, 600, 90, 25, 40, 70),
    ('COLLAGEN-1K', 'PA-009', '콜라겐 1000mg', '건강식품', '단품', 900, 1200, 250, 120, 100, 180),
    ('LUTEIN-20', 'PA-010', '루테인 20mg', '건강식품', '단품', 300, 400, 60, 90, 50, 40)
]

def create_table(conn):
    """Create the table if it doesn't exist"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS playauto_product_inventory 
    (
        마스터_sku VARCHAR(12) PRIMARY KEY, 
        플레이오토_sku VARCHAR(12), 
        상품명 TEXT, 
        카테고리 VARCHAR(10), 
        세트유무 VARCHAR(2) CHECK (세트유무 IN ('단품', '세트')), 
        출고량 INTEGER, 
        입고량 INTEGER, 
        현재재고 INTEGER, 
        리드타임 INTEGER, 
        최소주문수량 INTEGER, 
        안전재고 INTEGER, 
        제조사 VARCHAR(10), 
    );
    """
    
    with conn.cursor() as cursor:
        cursor.execute(create_table_query)
        conn.commit()
        print("테이블 생성 완료 (또는 이미 존재)")

def insert_sample_data(conn):
    """Insert sample data into the table"""
    # First, clear existing data to avoid duplicates
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM playauto_product_inventory")
        conn.commit()
        print("기존 데이터 삭제 완료")
    
    insert_query = """
    INSERT INTO playauto_product_inventory 
    (마스터_sku, 플레이오토_sku, 상품명, 카테고리, 세트유무, 출고량, 입고량, 현재재고, 리드타임, 최소주문수량, 안전재고)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    with conn.cursor() as cursor:
        for data in sample_data:
            cursor.execute(insert_query, data)
            print(f"삽입 완료: {data[2]} ({data[0]})")
        
        conn.commit()
        print(f"\n총 {len(sample_data)}개의 제품 데이터 처리 완료")

def verify_data(conn):
    """Verify the inserted data"""
    query = """
    SELECT 마스터_sku, 상품명, 현재재고, 안전재고,
           CASE 
               WHEN 현재재고 < 안전재고 * 0.5 THEN '긴급'
               WHEN 현재재고 < 안전재고 THEN '주의'
               ELSE '정상'
           END as 재고상태
    FROM playauto_product_inventory
    ORDER BY 마스터_sku;
    """
    
    with conn.cursor() as cursor:
        cursor.execute(query)
        results = cursor.fetchall()
        
        print("\n=== 재고 현황 확인 ===")
        print(f"{'마스터 SKU':<15} {'상품명':<25} {'현재재고':<10} {'안전재고':<10} {'상태':<10}")
        print("-" * 80)
        
        for row in results:
            print(f"{row[0]:<15} {row[1]:<25} {row[2]:<10} {row[3]:<10} {row[4]:<10}")

def main():
    """Main function to execute the data insertion"""
    try:
        # Connect to database
        conn = psycopg2.connect(**conn_params)
        print("데이터베이스 연결 성공")
        
        # Create table
        create_table(conn)
        
        # Insert sample data
        insert_sample_data(conn)
        
        # Verify data
        verify_data(conn)
        
    except psycopg2.Error as e:
        print(f"데이터베이스 오류: {e}")
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("\n데이터베이스 연결 종료")

if __name__ == "__main__":
    main()