import streamlit as st
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="PLAYAUTO - AI 재고 관리 시스템",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = "dashboard"

# Import database connection and queries
from config.database import db, ProductQueries
from utils.calculations import get_inventory_status, calculate_stockout_date

# Sidebar navigation
def sidebar_navigation():
    st.sidebar.title("PLAYAUTO")
    st.sidebar.markdown("---")
    
    # Navigation menu
    menu_items = {
        "대시보드": "dashboard",
        "제품 관리": "product_management",
        "재고 관리": "inventory",
        "수요 예측": "prediction",
        "알림 설정": "alerts"
    }
    
    for label, page in menu_items.items():
        if st.sidebar.button(label, use_container_width=True):
            st.session_state.current_page = page
    
    # User info and logout
    st.sidebar.markdown("---")
    st.sidebar.info("사용자: biocom")
    if st.sidebar.button("로그아웃", use_container_width=True):
        st.session_state.authenticated = False

# Main app
def main():
    # Check authentication (simplified for MVP)
    if not st.session_state.authenticated:
        st.title("PLAYAUTO 로그인")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                username = st.text_input("사용자명")
                password = st.text_input("비밀번호", type="password")
                if st.form_submit_button("로그인", use_container_width=True):
                    if username == "biocom" and password == "biocom":  # Simplified auth
                        st.session_state.authenticated = True
                        st.rerun()
                    else:
                        st.error("잘못된 사용자명 또는 비밀번호입니다.")
        return
    
    # Show sidebar
    sidebar_navigation()
    
    # Route to appropriate page
    if st.session_state.current_page == "dashboard":
        show_dashboard()
    elif st.session_state.current_page == "product_management":
        show_product_management()
    elif st.session_state.current_page == "inventory":
        show_inventory()
    elif st.session_state.current_page == "prediction":
        show_prediction()
    elif st.session_state.current_page == "alerts":
        show_alerts()

# Dashboard page
def show_dashboard():
    st.title("📊 실시간 재고 현황 대시보드")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    # Get metrics from database
    try:
        all_products = ProductQueries.get_all_products()
        if all_products:
            df_metrics = pd.DataFrame(all_products)
            total_products = len(df_metrics)
            low_stock = len(df_metrics[df_metrics['현재재고'] < df_metrics['안전재고']])
            critical_stock = len(df_metrics[df_metrics['현재재고'] < df_metrics['안전재고'] * 0.5])
            
            # Calculate products needing order within 7 days
            need_order_soon = 0
            for _, row in df_metrics.iterrows():
                daily_usage = row['출고량'] / 30 if row['출고량'] > 0 else 0
                if daily_usage > 0:
                    days_until_stockout = row['현재재고'] / daily_usage
                    if days_until_stockout <= 7:
                        need_order_soon += 1
        else:
            total_products = 0
            low_stock = 0
            critical_stock = 0
            need_order_soon = 0
    except:
        total_products = 0
        low_stock = 0
        critical_stock = 0
        need_order_soon = 0
    
    with col1:
        st.metric("전체 제품 수", f"{total_products}개", "0")
    with col2:
        st.metric("재고 부족 제품", f"{low_stock}개", f"+{critical_stock}", delta_color="inverse")
    with col3:
        st.metric("7일 내 발주 필요", f"{need_order_soon}개", "+0", delta_color="inverse")
    with col4:
        st.metric("예측 정확도", "92%", "+3%")
    
    st.markdown("---")
    
    # Inventory status table
    st.subheader("재고 현황")
    
    # Load data from PostgreSQL
    try:
        products = ProductQueries.get_all_products()
        if products:
            # Convert to DataFrame
            df = pd.DataFrame(products)
            
            # Calculate inventory status for each product
            inventory_data = pd.DataFrame()
            inventory_data['제품명'] = df['상품명']
            inventory_data['현재 재고'] = df['현재재고']
            inventory_data['안전재고'] = df['안전재고']
            
            # Calculate expected stockout date and status
            stockout_dates = []
            status_list = []
            
            for _, row in df.iterrows():
                # Calculate daily usage (출고량 / 30 days as approximation)
                daily_usage = row['출고량'] / 30 if row['출고량'] > 0 else 0
                
                # Calculate stockout date
                if daily_usage > 0:
                    days_until_stockout = row['현재재고'] / daily_usage
                    stockout_date = (datetime.now() + pd.Timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')
                else:
                    stockout_date = '재고 충분'
                stockout_dates.append(stockout_date)
                
                # Determine status
                if row['현재재고'] < row['안전재고'] * 0.5:
                    status = '긴급'
                elif row['현재재고'] < row['안전재고']:
                    status = '주의' 
                else:
                    status = '정상'
                status_list.append(status)
            
            inventory_data['예상 소진일'] = stockout_dates
            inventory_data['발주 필요'] = status_list
        else:
            # Fallback to sample data if no DB data
            inventory_data = pd.DataFrame({
                '제품명': ['데이터 없음'],
                '현재 재고': [0],
                '안전재고': [0],
                '예상 소진일': ['N/A'],
                '발주 필요': ['N/A']
            })
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {str(e)}")
        # Fallback to empty data
        inventory_data = pd.DataFrame({
            '제품명': ['연결 오류'],
            '현재 재고': [0],
            '안전재고': [0],
            '예상 소진일': ['N/A'],
            '발주 필요': ['오류']
        })
    
    # Color coding for status
    def highlight_status(row):
        if row['발주 필요'] == '긴급':
            return ['background-color: #ffcccc'] * len(row)
        elif row['발주 필요'] == '주의':
            return ['background-color: #f7dd65'] * len(row)
        return [''] * len(row)
    
    st.dataframe(
        inventory_data.style.apply(highlight_status, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    # Charts
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("월별 출고량 추이")
        st.line_chart(pd.DataFrame({
            '출고량': [3000, 3200, 2800, 3500, 3300, 3600]
        }))
    
    with col2:
        st.subheader("카테고리별 재고 현황")
        st.bar_chart(pd.DataFrame({
            '재고량': [500, 300, 450, 200]
        }, index=['비타민', '오메가3', '프로바이오틱스', '기타']))

# Product Management page
def show_product_management():
    st.title("🏷️ 제품 관리")
    
    tabs = st.tabs(["제품 목록", "신규 제품 등록", "리드타임 관리"])
    
    with tabs[0]:
        st.subheader("제품 목록")
        
        # Load product data from database
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                # Convert to DataFrame with renamed columns for display
                products_df = pd.DataFrame(products_data)
                products_df = products_df[['마스터_sku', '상품명', '카테고리', '최소주문수량', '리드타임', '안전재고']]
                products_df.columns = ['마스터 SKU', '상품명', '카테고리', 'MOQ', '리드타임(일)', '안전재고']
            else:
                # 데이터가 없으면 샘플 데이터를
                products_df = pd.DataFrame({
                    '(샘플) 마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                    '(샘플) 상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                    '(샘플) 카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                    '(샘플) MOQ': [100, 50, 30],
                    '(샘플) 리드타임(일)': [30, 45, 15],
                    '(샘플) 안전재고': [100, 100, 150]
                })
        except Exception as e:
            st.error(f"데이터베이스 오류: {str(e)}")
            # Fallback to sample data
            products_df = pd.DataFrame({
                '(샘플) 마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                '(샘플) 상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                '(샘플) 카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                '(샘플) MOQ': [100, 50, 30],
                '(샘플) 리드타임(일)': [30, 45, 15],
                '(샘플) 안전재고': [100, 100, 150]
            })
        
        # Editable dataframe
        edited_df = st.data_editor(
            products_df,
            use_container_width=True,
            num_rows="dynamic"
        )
        
        if st.button("변경사항 저장"):
            st.success("제품 정보가 업데이트되었습니다.")
    
    with tabs[1]:
        st.subheader("신규 제품 등록")
        
        with st.form("new_product_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                master_sku = st.text_input("마스터 SKU*")
                product_name = st.text_input("상품명*")
                category = st.selectbox("카테고리", ["비타민", "오메가3", "프로바이오틱스", "기타"])
            
            with col2:
                playauto_sku = st.text_input("플레이오토 SKU*")
                moq = st.number_input("최소주문수량(MOQ)", min_value=1, value=100)
                lead_time = st.number_input("리드타임(일)", min_value=1, value=30)
                safety_stock = st.number_input("안전재고", min_value=0, value=100)
            
            supplier = st.selectbox("공급업체", ["NPK", "다빈치랩", "바이오땡"])

            insert_sql = """
            INSERT INTO playauto_product_inventory(마스터_SKU, 상품명, 카테고리)
            """
            
            if st.form_submit_button("제품 등록"):
                st.success(f"제품 '{product_name}'이(가) 등록되었습니다.")
    
    with tabs[2]:
        st.subheader("공급업체별 리드타임 관리")
        
        supplier_data = pd.DataFrame({
            '공급업체': ['NPK', '다빈치랩', '바이오땡'],
            '기본 리드타임(일)': [120, 30, 45],
            '연락처': ['02-1234-5678', '02-2345-6789', '02-3456-7890']
        })
        
        st.data_editor(supplier_data, use_container_width=True)

# Inventory Management page
def show_inventory():
    st.title("📦 재고 관리")
    
    tabs = st.tabs(["템플릿 다운로드", "재고 업로드", "재고 조정"])
    
    with tabs[0]:
        st.subheader("재고 관리 템플릿 다운로드")
        st.info("엑셀 템플릿을 다운로드하여 입출고 수량을 입력한 후 업로드해주세요.")
        
        # Template download button
        if st.button("📥 템플릿 다운로드", use_container_width=True):
            # Load product data from database for template
            try:
                products_data = ProductQueries.get_all_products()
                if products_data:
                    df = pd.DataFrame(products_data)
                    template_df = pd.DataFrame({
                        '마스터 SKU': df['마스터_sku'],
                        '플레이오토 SKU': df['플레이오토_sku'],
                        '상품명': df['상품명'],
                        '카테고리': df['카테고리'],
                        '세트 유무': df['세트유무'],
                        '현재 재고': df['현재재고'],
                        '입고량': [0] * len(df),
                        '출고량': [0] * len(df)
                    })
                else:
                    # Fallback to sample template
                    template_df = pd.DataFrame({
                        '마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                        '플레이오토 SKU': ['PA-001', 'PA-002', 'PA-003'],
                        '상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                        '카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                        '세트 유무': ['단품', '단품', '세트'],
                        '현재 재고': [150, 45, 200],
                        '입고량': [0, 0, 0],
                        '출고량': [0, 0, 0]
                    })
            except:
                # Fallback to sample template
                template_df = pd.DataFrame({
                    '마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                    '플레이오토 SKU': ['PA-001', 'PA-002', 'PA-003'],
                    '상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                    '카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                    '세트 유무': ['단품', '단품', '세트'],
                    '현재 재고': [150, 45, 200],
                    '입고량': [0, 0, 0],
                    '출고량': [0, 0, 0]
                })
            
            # Convert to CSV for download
            csv = template_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="다운로드",
                data=csv,
                file_name=f"inventory_template_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    with tabs[1]:
        st.subheader("재고 데이터 업로드")
        
        uploaded_file = st.file_uploader(
            "재고 파일 업로드 (CSV, Excel)",
            type=['csv', 'xlsx', 'xls']
        )
        
        if uploaded_file is not None:
            # Read file
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.dataframe(df, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 재고 업데이트", use_container_width=True):
                    st.success("재고가 성공적으로 업데이트되었습니다.")
            with col2:
                if st.button("❌ 취소", use_container_width=True):
                    st.info("업로드가 취소되었습니다.")
    
    with tabs[2]:
        st.subheader("재고 조정")
        st.info("실제 재고와 시스템 재고가 다를 경우 조정할 수 있습니다.")
        
        # Get products from database
        products_list = ["비타민C 1000mg", "오메가3 500mg", "프로바이오틱스 10B"]  # Default fallback
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                products_list = [p['상품명'] for p in products_data]
        except:
            pass
        
        product = st.selectbox(
            "제품 선택",
            products_list
        )
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("현재 시스템 재고", "150개")
        with col2:
            actual_stock = st.number_input("실제 재고", min_value=0, value=150)
        
        reason = st.text_area("조정 사유")
        
        if st.button("재고 조정", use_container_width=True):
            st.success(f"{product}의 재고가 {actual_stock}개로 조정되었습니다.")

# Prediction page
def show_prediction():
    st.title("🔮 수요 예측")
    
    tabs = st.tabs(["예측 결과", "예측 모델 설정", "수동 조정"])
    
    with tabs[0]:
        st.subheader("AI 기반 수요 예측")
        
        # Product selection
        # Get products from database
        products_list = ["비타민C 1000mg", "오메가3 500mg", "프로바이오틱스 10B"]  # Default fallback
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                products_list = [p['상품명'] for p in products_data]
        except:
            pass
        
        product = st.selectbox(
            "제품 선택",
            products_list
        )
        
        # Prediction period
        period = st.radio(
            "예측 기간",
            ["30일", "60일", "90일"],
            horizontal=True
        )
        
        # Show prediction results
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("예측 출고량", "3,500개", "+12%")
        with col2:
            st.metric("권장 발주량", "4,000개", help="MOQ 및 안전재고 고려")
        with col3:
            st.metric("예측 정확도", "89%", help="RMSE 기반")
        
        # Prediction chart
        st.subheader("예측 차트")
        prediction_data = pd.DataFrame({
            '날짜': pd.date_range(start='2025-01-01', periods=90, freq='D'),
            '실제': [100 + i*2 + (i%7)*10 for i in range(90)],
            '예측': [105 + i*2 + (i%7)*8 for i in range(90)]
        })
        st.line_chart(prediction_data.set_index('날짜'))
        
        # Safety stock calculation
        st.subheader("안전재고 계산")
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"""
            **계산 방식**
            - 30일 예측 출고량: 3,500개
            - 리드타임: 30일
            - 안전재고 = 3,500 × (30/30) = 3,500개
            """)
        with col2:
            st.metric("권장 안전재고", "3,500개")
            st.metric("현재 설정값", "3,000개", "-500개")
    
    with tabs[1]:
        st.subheader("예측 모델 설정")
        
        model = st.selectbox(
            "예측 모델 선택",
            ["Prophet (권장)", "ARIMA", "LSTM"]
        )
        
        st.info(f"현재 선택된 모델: {model}")
        
        # Model parameters
        if model == "Prophet (권장)":
            seasonality = st.checkbox("계절성 고려", value=True)
            holidays = st.checkbox("휴일 효과 고려", value=True)
        elif model == "ARIMA":
            p = st.slider("p (자기회귀)", 0, 5, 1)
            d = st.slider("d (차분)", 0, 2, 1)
            q = st.slider("q (이동평균)", 0, 5, 1)
        
        if st.button("모델 재학습"):
            with st.spinner("모델을 재학습하고 있습니다..."):
                # Simulate training
                import time
                time.sleep(2)
            st.success("모델 재학습이 완료되었습니다.")
    
    with tabs[2]:
        st.subheader("예측값 수동 조정")
        st.warning("수동으로 조정한 값은 이력이 기록됩니다.")
        
        # Manual adjustment form
        with st.form("manual_adjustment"):
            product = st.selectbox(
                "제품",
                ["비타민C 1000mg", "오메가3 500mg", "프로바이오틱스 10B"]
            )
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("AI 예측값", "3,500개")
                adjusted_value = st.number_input(
                    "조정값",
                    min_value=0,
                    value=3500
                )
            
            with col2:
                adjustment_reason = st.text_area(
                    "조정 사유",
                    placeholder="예: 프로모션 예정, 계절적 요인 등"
                )
            
            if st.form_submit_button("조정 저장"):
                st.success(f"예측값이 {adjusted_value}개로 조정되었습니다.")
                st.info(f"조정자: biocom | 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Alerts page
def show_alerts():
    st.title("🔔 알림 설정")
    
    tabs = st.tabs(["알림 목록", "알림 설정", "알림 이력"])
    
    with tabs[0]:
        st.subheader("활성 알림")
        
        # Alert types
        alert_types = st.multiselect(
            "알림 유형 필터",
            ["재고 부족", "발주 시점", "소비기한 임박", "과잉 재고"],
            default=["재고 부족", "발주 시점"]
        )
        
        # Active alerts
        alerts_data = pd.DataFrame({
            '유형': ['재고 부족', '발주 시점', '재고 부족', '소비기한 임박'],
            '제품': ['오메가3 500mg', '비타민C 1000mg', '프로바이오틱스 10B', '비타민D'],
            '상태': ['긴급', '주의', '긴급', '경고'],
            '메시지': [
                '재고 45개, 7일 내 소진 예상',
                '15일 후 발주 필요 (리드타임 30일)',
                '재고 30개, 5일 내 소진 예상',
                '소비기한 30일 남음'
            ],
            '발생일시': pd.date_range(end=datetime.now(), periods=4, freq='2H')
        })
        
        # Color code by status
        def color_status(val):
            if val == '긴급':
                return 'background-color: #ff4444; color: white'
            elif val == '경고':
                return 'background-color: #ff8800; color: white'
            elif val == '주의':
                return 'background-color: #ffaa00'
            return ''
        
        styled_df = alerts_data.style.applymap(
            color_status, 
            subset=['상태']
        )
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Quick actions
        if st.button("📋 발주표 생성"):
            st.success("발주표가 생성되었습니다.")
            
            # Show order sheet
            order_sheet = pd.DataFrame({
                '제품': ['오메가3 500mg', '프로바이오틱스 10B'],
                '현재 재고': [45, 30],
                '권장 발주량': [500, 300],
                'MOQ': [50, 30],
                '공급업체': ['다빈치랩', 'NPK'],
                '예상 입고일': ['2025-02-15', '2025-02-10']
            })
            st.dataframe(order_sheet, use_container_width=True, hide_index=True)
    
    with tabs[1]:
        st.subheader("알림 설정")
        
        # Notification settings
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**재고 부족 알림**")
            stock_alert_days = st.slider(
                "재고 소진 예상일 기준 (일)",
                1, 30, 10,
                help="재고가 N일 내에 소진될 것으로 예상되면 알림"
            )
            
            st.markdown("**발주 시점 알림**")
            order_alert_days = st.slider(
                "발주 필요일 전 알림 (일)",
                1, 30, 10,
                help="발주가 필요한 시점 N일 전에 알림"
            )
        
        with col2:
            st.markdown("**소비기한 알림**")
            expiry_alert_days = st.slider(
                "소비기한 임박 기준 (일)",
                7, 90, 30,
                help="소비기한이 N일 남으면 알림"
            )
            
            st.markdown("**과잉 재고 알림**")
            overstock_ratio = st.slider(
                "과잉 재고 비율 (%)",
                100, 500, 200,
                help="안전재고 대비 N% 이상이면 알림"
            )
        
        # Notification channels
        st.markdown("**알림 채널**")
        email_notify = st.checkbox("이메일 알림", value=True)
        if email_notify:
            email = st.text_input("이메일 주소", value="biocom@example.com")
        
        sms_notify = st.checkbox("SMS 알림")
        if sms_notify:
            phone = st.text_input("휴대폰 번호", value="010-1234-5678")
        
        if st.button("설정 저장", use_container_width=True):
            st.success("알림 설정이 저장되었습니다.")
    
    with tabs[2]:
        st.subheader("알림 이력")
        
        # Date range filter
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("시작일", value=datetime.now().date())
        with col2:
            end_date = st.date_input("종료일", value=datetime.now().date())
        
        # Alert history
        history_data = pd.DataFrame({
            '일시': pd.date_range(end=datetime.now(), periods=10, freq='6H'),
            '유형': ['재고 부족'] * 5 + ['발주 시점'] * 5,
            '제품': ['비타민C', '오메가3', '프로바이오틱스'] * 3 + ['비타민D'],
            '상태': ['처리완료', '미처리', '처리완료'] * 3 + ['미처리'],
            '처리자': ['biocom', '-', 'biocom'] * 3 + ['-']
        })
        
        st.dataframe(history_data, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()