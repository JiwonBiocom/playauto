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

# Sample data for 10 products based on save_data.py 출고량 values
# Using the 출고량 column as a baseline for monthly averages
sample_data = [
    # (마스터_SKU, 입출고_여부, 수량, 시점)
    ('VIT-C-1000', 'PA-001', '비타민C 1000mg', 280, 265, 250, 245, 240, 220),  # Total ~1500, avg 250/month
    ('OMEGA-3-500', 'PA-002', '오메가3 500mg', 360, 350, 340, 330, 320, 300),  # Total ~2000, avg 333/month
    ('PROBIO-10B', 'PA-003', '프로바이오틱스 10B', 180, 175, 170, 165, 160, 150),  # Total ~1000, avg 167/month
    ('VIT-D-5000', 'PA-004', '비타민D 5000IU', 145, 140, 135, 130, 130, 120),  # Total ~800, avg 133/month
    ('MULTI-VIT', 'PA-005', '종합비타민', 220, 210, 205, 195, 190, 180),  # Total ~1200, avg 200/month
    ('CALCIUM-MAG', 'PA-006', '칼슘&마그네슘', 110, 105, 100, 100, 95, 90),  # Total ~600, avg 100/month
    ('IRON-18', 'PA-007', '철분 18mg', 75, 70, 68, 65, 62, 60),  # Total ~400, avg 67/month
    ('ZINC-15', 'PA-008', '아연 15mg', 90, 88, 85, 82, 80, 75),  # Total ~500, avg 83/month
    ('COLLAGEN-1K', 'PA-009', '콜라겐 1000mg', 165, 160, 155, 150, 145, 125),  # Total ~900, avg 150/month
    ('LUTEIN-20', 'PA-010', '루테인 20mg', 55, 52, 50, 50, 48, 45)  # Total ~300, avg 50/month
]

def create_table(conn):
    """Create the shipment table if it doesn't exist"""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS playauto_shipment 
    (
        마스터_SKU VARCHAR(12), 
        플레이오토_SKU VARCHAR(12),
        상품명 TEXT, 
        출고량_1개월전 INTEGER, 
        출고량_2개월전 INTEGER, 
        출고량_3개월전 INTEGER, 
        출고량_4개월전 INTEGER, 
        출고량_5개월전 INTEGER, 
        출고량_6개월전 INTEGER,
        PRIMARY KEY (마스터_SKU)
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
        cursor.execute("DELETE FROM playauto_shipment")
        conn.commit()
        print("기존 데이터 삭제 완료")
    
    insert_query = """
    INSERT INTO playauto_shipment 
    (마스터_SKU, 플레이오토_SKU, 상품명, 출고량_1개월전, 출고량_2개월전, 
     출고량_3개월전, 출고량_4개월전, 출고량_5개월전, 출고량_6개월전)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    with conn.cursor() as cursor:
        for data in sample_data:
            cursor.execute(insert_query, data)
            print(f"삽입 완료: {data[2]} - 최근 6개월 출고량: {data[3:]}")
        
        conn.commit()
        print(f"\n총 {len(sample_data)}개의 제품 출고 데이터 처리 완료")

def verify_data(conn):
    """Verify the inserted shipment data"""
    query = """
    SELECT 마스터_SKU, 상품명, 
           출고량_1개월전, 출고량_2개월전, 출고량_3개월전,
           출고량_4개월전, 출고량_5개월전, 출고량_6개월전,
           (출고량_1개월전 + 출고량_2개월전 + 출고량_3개월전 + 
            출고량_4개월전 + 출고량_5개월전 + 출고량_6개월전) as 총출고량,
           ROUND((출고량_1개월전 + 출고량_2개월전 + 출고량_3개월전 + 
                  출고량_4개월전 + 출고량_5개월전 + 출고량_6개월전) / 6.0, 1) as 월평균
    FROM playauto_shipment
    ORDER BY 총출고량 DESC;
    """
    
    with conn.cursor() as cursor:
        cursor.execute(query)
        results = cursor.fetchall()
        
        print("\n=== 출고량 통계 확인 ===")
        print(f"{'마스터 SKU':<15} {'상품명':<25} {'1개월전':<10} {'2개월전':<10} {'3개월전':<10} {'총출고량':<10} {'월평균':<10}")
        print("-" * 100)
        
        for row in results:
            print(f"{row[0]:<15} {row[1]:<25} {row[2]:<10} {row[3]:<10} {row[4]:<10} {row[8]:<10} {row[9]:<10}")

def main():
    """Main function to execute the shipment data insertion"""
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