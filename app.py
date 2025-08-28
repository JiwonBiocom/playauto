import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
import io
import pickle
import numpy as np
import secrets
import hashlib
import plotly.graph_objects as go

import time
import datetime as dt
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Import database connection and queries
from config.database import db, MemberQueries, ProductQueries, ShipmentQueries, PredictionQueries
from utils.calculations import get_inventory_status, calculate_stockout_date
from utils.email_alerts import EmailAlertSystem
from utils.notification_scheduler import NotificationScheduler
from utils.order_timing import calculate_reorder_point, calculate_demand_trend, batch_calculate_reorder_points

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
if 'member_join' not in st.session_state:
    st.session_state.member_join = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = "dashboard"
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

# Sidebar navigation
def sidebar_navigation():
    st.sidebar.title("PLAYAUTO")
    st.sidebar.markdown("---")
    
    # Navigation menu
    menu_items = {
        "대시보드": "dashboard",
        "출고량 통계": "shipment_quantity", 
        "제품 관리": "product_management",
        "재고 관리": "inventory",
        "수요 예측": "prediction",
        "알림": "alerts"
    }
    
    for label, page in menu_items.items():
        if st.sidebar.button(label, use_container_width=True):
            st.session_state.current_page = page
    
    # User info and logout
    st.sidebar.markdown("---")
    st.sidebar.info(f"""{st.session_state.user_info['name']} ({st.session_state.user_id})님 환영합니다.""")
    
    if MemberQueries.get_member_by_id(st.session_state.user_id)['master'] == True:
        if st.sidebar.button("관리자", use_container_width=True):
            st.session_state.current_page = "member_management"
    
    if st.sidebar.button("회원 정보", use_container_width=True):
        st.session_state.current_page = "member"
    if st.sidebar.button("로그아웃", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.session_state.user_info = None
        st.rerun()
    

# Member join page
def show_member_join():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("PLAYAUTO 회원가입")
        with st.form("join_form"):
            st.subheader("회원 정보 입력")
            
            # Basic information
            username = st.text_input("사용자명 *", help="로그인에 사용할 ID를 입력하세요")
            password = st.text_input("비밀번호 *", type="password", help="6자 이상 입력하세요")
            password_confirm = st.text_input("비밀번호 확인 *", type="password")
            
            st.markdown("---")
            
            # Personal information
            name = st.text_input("이름 *")
            email = st.text_input("이메일 *", help="example@email.com")
            phone = st.text_input("전화번호", help="010-1234-5678")
            
            # Submit button
            if st.form_submit_button("가입하기", use_container_width=True):
                # Validation
                if not all([username, password, password_confirm, name, email]):
                    st.error("필수 항목(*)을 모두 입력해주세요.")
                elif len(password) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                elif password != password_confirm:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    try:
                        # Insert member into database
                        # Using 'N' as default for master field (assuming it's a Yes/No field)
                        result = MemberQueries.insert_member(
                            id=username,
                            password=password,
                            name=name,
                            master=False,  # Default value for regular users
                            email=email,
                            phone_no=phone or ''  # Empty string if phone is not provided
                        )
                        
                        if result:
                            st.success(f"회원가입이 완료되었습니다! 사용자명: {username}")
                            st.info("잠시 후 로그인 페이지로 이동합니다...")
                            time.sleep(3)
                            
                            # Reset member_join state and redirect to login
                            st.session_state.member_join = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"회원가입 중 오류가 발생했습니다: {str(e)}")
        
        # Back to login button
        if st.button("로그인 페이지로 돌아가기", use_container_width=True):
            st.session_state.member_join = False
            st.rerun()

# Main app
def main():
    # Check authentication (simplified for MVP)
    if not st.session_state.authenticated:
        # Check if user wants to join
        if st.session_state.member_join:
            show_member_join()
            return

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("PLAYAUTO: 이커머스를 위한 플랫폼")
            with st.form("login_form"):
                st.subheader("로그인")
                username = st.text_input("사용자명")
                password = st.text_input("비밀번호", type="password")
                if st.form_submit_button("로그인", use_container_width=True):
                    # Verify credentials against database
                    user = MemberQueries.verify_login(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user_info = user
                        st.session_state.user_id = user['id']
                        st.session_state.user_name = user['name']
                        st.rerun()
                    else:
                        st.error("잘못된 사용자명 또는 비밀번호입니다.")
            
            # 회원 가입
            if st.button("회원가입"):
                st.session_state.member_join = True
                st.rerun()
        
        return
    
    # Show sidebar
    sidebar_navigation()
    
    # Route to appropriate page
    if st.session_state.current_page == "dashboard":
        show_dashboard()
    if st.session_state.current_page == 'shipment_quantity':
        show_shipment_quantity()
    elif st.session_state.current_page == "product_management":
        show_product_management()
    elif st.session_state.current_page == "inventory":
        show_inventory()
    elif st.session_state.current_page == "prediction":
        show_prediction()
    elif st.session_state.current_page == "alerts":
        show_alerts()
    elif st.session_state.current_page == 'member':
        member_info()
    elif st.session_state.current_page == 'member_management':
        show_member_management()

# Dashboard page
def show_dashboard():
    st.title("📊 실시간 재고 현황 대시보드")
    
    # Key metrics
    col1, col2, col3 = st.columns(3)
    
    # Get metrics from database
    try:
        all_products = ProductQueries.get_all_products()
        if all_products:
            df_metrics = pd.DataFrame(all_products)
            # Convert numeric columns to handle NaN/inf values
            df_metrics['현재재고'] = pd.to_numeric(df_metrics['현재재고'], errors='coerce').fillna(0)
            df_metrics['안전재고'] = pd.to_numeric(df_metrics['안전재고'], errors='coerce').fillna(0)
            df_metrics['출고량'] = pd.to_numeric(df_metrics['출고량'], errors='coerce').fillna(0)
            df_metrics['리드타임'] = pd.to_numeric(df_metrics['리드타임'], errors='coerce').fillna(0)
            
            total_products = len(df_metrics)
            low_stock = len(df_metrics[df_metrics['현재재고'] < df_metrics['안전재고']])
            critical_stock = len(df_metrics[df_metrics['현재재고'] < df_metrics['안전재고'] * 0.5])
            
            # Calculate products needing order within 7 days
            need_order_soon = 0
            for _, row in df_metrics.iterrows():
                daily_usage = row['출고량'] / 30 if row['출고량'] and row['출고량'] > 0 else 0
                if daily_usage > 0:
                    days_until_stockout = row['현재재고'] / daily_usage
                    days_until_reorder_needed = days_until_stockout - row['리드타임']
                    # Only count products that need ordering within 0-7 days (not overdue ones)
                    if 0 <= days_until_reorder_needed <= 7:
                        need_order_soon += 1
        else:
            total_products = 0
            low_stock, critical_stock = 0, 0
            need_order_soon = 0
    except:
        total_products = 0
        low_stock, critical_stock = 0, 0
        need_order_soon = 0
    
    with col1:
        st.metric("전체 제품 수", f"{total_products}개", "")  # 제품이 추가될 때마다 상승
    with col2:
        st.metric("재고 부족 제품", f"{low_stock}개", f"", delta_color="inverse") # f"+{critical_stock}"
    with col3:
        st.metric("7일 내 발주 필요", f"{need_order_soon}개", "", delta_color="inverse")  # 발주 필요 제품이 늘어날 때마다 상승
    # with col4:
    #     st.metric("예측 정확도", "92% (임시)", "+3% (임시)")
    
    st.markdown("---")
    
    # 상품별 재고 현황
    st.subheader("상품별 재고 현황")
    
    # Load data from PostgreSQL
    try:
        products = ProductQueries.get_all_products()
        if products:
            # Convert to DataFrame
            df = pd.DataFrame(products)
            
            # Calculate inventory status for each product
            inventory_data = pd.DataFrame()
            inventory_data['제품명'] = df['상품명']
            # Handle NaN, None, and inf values in 현재재고
            inventory_data['현재재고'] = pd.to_numeric(df['현재재고'], errors='coerce').fillna(0).astype(int)
            inventory_data['안전재고'] = pd.to_numeric(df['안전재고'], errors='coerce').fillna(0).astype(int)
            inventory_data['리드타임(일)'] = pd.to_numeric(df['리드타임'], errors='coerce').fillna(0)
            
            # Calculate expected stockout date and status
            stockout_dates = []
            status_list = []
            need_order_7days = []
            
            for _, row in df.iterrows():
                # Calculate daily usage (출고량 / 30 days as approximation)
                daily_usage = row['출고량'] / 30 if row['출고량'] and row['출고량'] > 0 else 0
                
                # Calculate stockout date and check if needs ordering within 7 days
                if daily_usage > 0:
                    days_until_stockout = row['현재재고'] / daily_usage
                    stockout_date = (datetime.now() + pd.Timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')
                    
                    # Check if needs ordering within 7 days
                    lead_time = pd.to_numeric(row['리드타임'], errors='coerce')
                    lead_time = 0 if pd.isna(lead_time) else lead_time
                    days_until_reorder_needed = days_until_stockout - lead_time
                    
                    # Only mark as needing order within 7 days if it's between 0 and 7 days
                    # Negative values mean it's already overdue (should have been ordered already)
                    if 0 <= days_until_reorder_needed <= 7:
                        need_order_7days.append('✓')
                    elif days_until_reorder_needed < 0:
                        need_order_7days.append('⚠️ 기간 지남')  # Already overdue
                    else:
                        need_order_7days.append('')
                else:  # 출고량 없음
                    stockout_date = ''
                    need_order_7days.append('')
                stockout_dates.append(stockout_date)
                
                # Determine status
                if row['현재재고'] < row['안전재고'] * 0.5:
                    status = '긴급'
                elif row['현재재고'] < row['안전재고']:
                    status = '주의' 
                else:
                    status = '정상'
                status_list.append(status)
            
            inventory_data['재고 소진 예상일'] = stockout_dates
            inventory_data['발주 필요 여부'] = status_list
            inventory_data['7일 내 발주 필요'] = need_order_7days
        else:
            # Fallback to sample data if no DB data
            inventory_data = pd.DataFrame({
                '제품명': ['데이터 없음'],
                '현재재고': [0],
                '안전재고': [0],
                '리드타임': [0],
                '재고 소진 예상일': ['N/A'],
                '발주 필요 여부': ['N/A'],
                '7일 내 발주 필요': ['']
            })
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {str(e)}")
        # Fallback to empty data
        inventory_data = pd.DataFrame({
            '제품명': ['연결 오류'],
            '현재재고': [0],
            '안전재고': [0],
            '리드타임': [0],
            '재고 소진 예상일': ['N/A'],
            '발주 필요 여부': ['오류'],
            '7일 내 발주 필요': ['']
        })
    
    # Color coding for status
    def highlight_status(row):
        if row['발주 필요 여부'] == '긴급':
            return ['background-color: #ffcccc'] * len(row)
        elif row['발주 필요 여부'] == '주의':
            return ['background-color: #f7dd65'] * len(row)
        # elif row['7일 내 발주 필요'] == '✓':
        #     return ['background-color: #ffe4b5'] * len(row)  # Light orange for 7-day order needed
        return [''] * len(row)
    
    st.dataframe(
        inventory_data.style.apply(highlight_status, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    # 바 그래프
    try:
        all_products = ProductQueries.get_all_products()
        if all_products:
            df_products = pd.DataFrame(all_products)
            
            # Calculate status for each product
            colors = []
            product_names = []
            inventory_values = []
            
            for _, product in df_products.iterrows():
                # product_names.append(product['상품명'])
                product_names = [
                    '바이오밸런스', '풍성밸런스', '클린밸런스', 
                    '뉴로마스터', '키네코어', '다래 케어', 
                    '선화이버', '영데이즈', '당당케어', 
                    '칸디다웨이', '퓨어마그 펫'
                ]
                inventory_values.append(product['현재재고'])
                
                # Determine color based on stock status
                current = product['현재재고'] if product['현재재고'] is not None else 0
                safety = product['안전재고'] if product['안전재고'] is not None else 0
                
                if current < safety * 0.5:
                    colors.append('#ff4444')  # Red for emergency
                elif current < safety:
                    colors.append('#ff9944')  # Orange for warning
                else:
                    colors.append('#4444ff')  # Blue for normal
            
            # 바 그래프 생성
            if product_names:
                fig = go.Figure(data=[
                    go.Bar(
                        x=product_names,
                        y=inventory_values,
                        marker_color=colors,
                        text=inventory_values,
                        textposition='auto'
                    )
                ])
                
                fig.update_layout(
                    xaxis_title="제품명",
                    yaxis_title="재고량",
                    showlegend=False,
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("제품별 재고 데이터가 없습니다.")
        else:
            # Fallback to sample data if no products
            st.bar_chart(pd.DataFrame({
                '재고량': [0]
            }, index=['데이터 없음']))
    except Exception as e:
        st.error(f"데이터 로드 오류: {str(e)}")
        # Fallback to sample data on error
        st.bar_chart(pd.DataFrame({
            '재고량': [0]
        }, index=['오류']))

# 출고량 확인
def show_shipment_quantity():
    st.title("📊 출고량 통계")
    # tabs = st.tabs(["출고량 확인", "-"])
    
    st.subheader("지난 6개월간 출고량")
    st.info("지난 6개월간의 상품별 월간 출고량입니다.")
    
    try:
        # 월간 출고량 불러오기
        shipment_data = ShipmentQueries.get_monthly_shipment_summary()
        
        if shipment_data:
            df_shipment = pd.DataFrame(shipment_data)
            
            # Reorder columns for display
            display_columns = [
                '마스터_sku', '상품명',
                '출고량_5개월전', '출고량_4개월전', '출고량_3개월전', 
                '출고량_2개월전', '출고량_1개월전', '출고량_현재월'
            ]
            df_display = df_shipment[display_columns]
            
            # 현재 시간 기준으로 월 변경
            current_date = datetime.now()
            month_names = []
            for i in range(5, -1, -1):  # 6 months ago to 1 month ago
                target_date = current_date - relativedelta(months=i)
                month_name = f"{str(target_date.year)[2:]}년_{target_date.month}월"
                month_names.append(month_name)
            
            # Rename columns for better display
            df_display.columns = ['마스터 SKU', '상품명'] + month_names
            
            # 테이블 보기
            with st.expander("📊 제품별 출고량 데이터 테이블", expanded=False):
                st.dataframe(
                    df_display,
                    column_config={
                        "마스터 SKU": st.column_config.TextColumn(
                            "마스터 SKU",
                            width=100,  # or specific pixel value like 100
                        ),
                        "상품명": st.column_config.TextColumn(
                            "상품명",
                            width=100,  # or specific pixel value like 200
                        ),
                        "출고량_5개월전": st.column_config.TextColumn(
                            "출고량_5개월전",
                            width=100,  # or specific pixel value like 200
                        ),
                    },
                    use_container_width=True,
                    hide_index=True
                )
            

            # 제품별 출고량 추이
            st.subheader("제품별 출고량 추이")
            
            # Select product for individual visualization
            product_list = df_display['상품명'].tolist()
            selected_product = st.selectbox("제품 선택", product_list)
            
            # Debug: Check if we have data
            if len(df_display) == 0:
                st.warning("표시할 데이터가 없습니다.")
            else:
                # Get the selected product's data
                selected_row = df_display[df_display['상품명'] == selected_product].iloc[0]
                
                # Prepare data for line chart
                months = month_names  # Use the dynamically generated month names
                values = []
                
                # Extract values for each month
                for month in months:
                    try:
                        value = float(selected_row[month]) if selected_row[month] is not None else 0
                    except:
                        value = 0
                    values.append(value)
                
                # Create chart dataframe
                chart_df = pd.DataFrame(
                    {'출고량': values}, 
                    index=months
                )
                
                # Display line chart
                st.line_chart(chart_df)
            
            
            # 제품별 출고량 추이
            st.subheader("최근 1년간 출고량 추이 다운로드")

            # Get all shipment data for the last year
            all_shipments = ShipmentQueries.get_all_inv_out()
            
            if all_shipments:
                # Convert to DataFrame
                df_all_shipments = pd.DataFrame(all_shipments)
                
                # Convert 시점 to datetime
                df_all_shipments['시점'] = pd.to_datetime(df_all_shipments['시점'])
                
                # Filter data for last 1 year
                end_date = datetime.now().date()
                start_date = end_date - relativedelta(years=1)
                
                # If no data for today, use the latest available date
                latest_date = df_all_shipments['시점'].max().date()
                if latest_date < end_date:
                    end_date = latest_date
                    start_date = end_date - relativedelta(years=1)
                
                # Filter data within the date range
                df_filtered = df_all_shipments[
                    (df_all_shipments['시점'].dt.date > start_date) & 
                    (df_all_shipments['시점'].dt.date <= end_date)
                ].copy()
                
                if not df_filtered.empty:
                    # Group by product and date (daily)
                    df_filtered['날짜'] = df_filtered['시점'].dt.date
                    pivot_data = df_filtered.pivot_table(
                        index='마스터_sku',
                        columns='날짜',
                        values='수량',
                        aggfunc='sum',
                        fill_value=0
                    )
                    
                    # Get product names
                    products = ProductQueries.get_all_products()
                    product_names = {p['마스터_sku']: p['상품명'] for p in products}
                    
                    # Reset index and add product names
                    pivot_data = pivot_data.reset_index()
                    pivot_data.insert(1, '상품명', pivot_data['마스터_sku'].map(product_names))
                    
                    # Sort columns in reverse chronological order (latest date first)
                    date_columns = [col for col in pivot_data.columns if isinstance(col, dt.date)]
                    date_columns.sort(reverse=True)
                    final_columns = ['마스터_sku', '상품명'] + date_columns
                    pivot_data = pivot_data[final_columns]
                    
                    # Format column names as strings (YYYY-MM-DD)
                    pivot_data.columns = ['마스터_SKU', '상품명'] + [col.strftime('%Y-%m-%d') for col in date_columns]
                    
                    # Create Excel file
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        pivot_data.to_excel(writer, index=False, sheet_name='출고량_추이')
                        
                        # Add summary sheet with monthly totals
                        df_monthly = df_filtered.copy()
                        df_monthly['년월'] = df_monthly['시점'].dt.to_period('M')
                        monthly_summary = df_monthly.pivot_table(
                            index='마스터_sku',
                            columns='년월',
                            values='수량',
                            aggfunc='sum',
                            fill_value=0
                        )
                        monthly_summary = monthly_summary.reset_index()
                        monthly_summary.insert(1, '상품명', monthly_summary['마스터_sku'].map(product_names))
                        
                        # Format month columns
                        month_columns = [col for col in monthly_summary.columns if col not in ['마스터_sku', '상품명']]
                        month_columns = sorted(month_columns, reverse=True)
                        monthly_summary = monthly_summary[['마스터_sku', '상품명'] + month_columns]
                        
                        # Convert period columns to strings
                        monthly_summary.columns = ['마스터_SKU', '상품명'] + [str(col) for col in month_columns]
                        
                        monthly_summary.to_excel(writer, index=False, sheet_name='월별_출고량')
                    
                    # Download button
                    st.download_button(
                        label=f"📥 출고량 추이 다운로드 ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})",
                        data=buffer.getvalue(),
                        file_name=f"shipment_trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    
                    # st.success(f"✅ 다운로드 준비 완료: {len(pivot_data)}개 제품의 최근 1년간 출고 데이터")
                else:
                    st.warning("최근 1년간 출고 데이터가 없습니다.")
            else:
                st.warning("출고 데이터가 없습니다.")
            
        else:
            st.warning("출고 데이터가 없습니다.")
            st.info("playauto_shipment_receipt 테이블에 데이터를 추가해주세요.")
            
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {str(e)}")
        st.info("데이터베이스 연결을 확인하거나 테이블 구조를 확인해주세요.")

# Product Management page
def show_product_management():
    st.title("🏷️ 제품 관리")
    
    tabs = st.tabs(["제품 정보 수정", "신규 제품 등록"])
    
    with tabs[0]:
        st.subheader("제품 정보 수정")
        st.info("아래 제품의 최소주문수량, 리드타임, 안전재고, 소비기한 정보를 수정하시고 변경사항 저장을 누르세요.")

        # Show success message if exists in session state
        if 'product_update_message' in st.session_state:
            st.success(st.session_state.product_update_message)
            del st.session_state.product_update_message
        
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                # Convert to DataFrame with renamed columns for display
                products_df = pd.DataFrame(products_data)
                products_df = products_df[['마스터_sku', '상품명', '카테고리', '최소주문수량', '리드타임', '안전재고', '소비기한', '제조사']]
                products_df.columns = ['마스터 SKU', '상품명', '카테고리', '최소주문수량', '리드타임', '안전재고', '소비기한', '제조사']
            else:
                # 데이터가 없으면 샘플 데이터를
                products_df = pd.DataFrame({
                    '(샘플) 마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                    '(샘플) 상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                    '(샘플) 카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                    '(샘플) MOQ': [100, 50, 30],
                    '(샘플) 리드타임(일)': [30, 45, 15],
                    '(샘플) 안전재고': [100, 100, 150], 
                    '(샘플) 제조사': ['', '', '']
                })
        except Exception as e:
            st.error(f"데이터베이스 오류: {str(e)}")
            # 연결 실패해도 샘플 데이터를
            products_df = pd.DataFrame({
                '(샘플) 마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                '(샘플) 상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                '(샘플) 카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                '(샘플) MOQ': [100, 50, 30],
                '(샘플) 리드타임(일)': [30, 45, 15],
                '(샘플) 안전재고': [100, 100, 150], 
                '(샘플) 제조사': ['', '', '']
            })
        
        # 제품 수정 가능한 테이블
        edited_df = st.data_editor(
            products_df,
            use_container_width=True,
            num_rows="dynamic",
            key="products_editor"
        )
        
        if st.button("변경사항 저장"):
            try:
                # Compare original and edited dataframes to find changes
                if len(products_df) == len(edited_df):
                    changes_made = False
                    errors = []
                    
                    for idx in range(len(products_df)):
                        # 수정됐는지 확인
                        row_changed = False
                        updates = {}
                        
                        master_sku = products_df.iloc[idx]['마스터 SKU']
                        
                        # 수정
                        if products_df.iloc[idx]['최소주문수량'] != edited_df.iloc[idx]['최소주문수량']:
                            try:
                                # Clean the value before converting
                                val = str(edited_df.iloc[idx]['최소주문수량']).replace('│', '').replace('|', '').strip()
                                updates['최소주문수량'] = int(float(val))
                            except:
                                try:
                                    # Also clean the original value as fallback
                                    orig_val = str(products_df.iloc[idx]['최소주문수량']).replace('│', '').replace('|', '').strip()
                                    updates['최소주문수량'] = int(float(orig_val))
                                except:
                                    updates['최소주문수량'] = 1  # Default minimum order quantity
                            row_changed = True
                        
                        if products_df.iloc[idx]['리드타임'] != edited_df.iloc[idx]['리드타임']:
                            try:
                                # Clean the value before converting
                                val = str(edited_df.iloc[idx]['리드타임']).replace('│', '').replace('|', '').strip()
                                updates['리드타임'] = int(float(val))
                            except:
                                try:
                                    # Also clean the original value as fallback
                                    orig_val = str(products_df.iloc[idx]['리드타임']).replace('│', '').replace('|', '').strip()
                                    updates['리드타임'] = int(float(orig_val))
                                except:
                                    updates['리드타임'] = 7  # Default lead time
                            row_changed = True
                        
                        if products_df.iloc[idx]['안전재고'] != edited_df.iloc[idx]['안전재고']:
                            try:
                                # Clean the value before converting
                                val = str(edited_df.iloc[idx]['안전재고']).replace('│', '').replace('|', '').strip()
                                updates['안전재고'] = int(float(val))
                            except:
                                try:
                                    # Also clean the original value as fallback
                                    orig_val = str(products_df.iloc[idx]['안전재고']).replace('│', '').replace('|', '').strip()
                                    updates['안전재고'] = int(float(orig_val))
                                except:
                                    updates['안전재고'] = 100  # Default safety stock
                            row_changed = True
                        
                        if products_df.iloc[idx]['소비기한'] != edited_df.iloc[idx]['소비기한']:
                            updates['소비기한'] = edited_df.iloc[idx]['소비기한']
                            row_changed = True
                        
                        # if products_df.iloc[idx]['제조사'] != edited_df.iloc[idx]['제조사']:
                        #     updates['제조사'] = edited_df.iloc[idx]['제조사']
                        #     row_changed = True
                        
                        # 수정 사항이 있으면 데이터베이스 업데이트
                        if row_changed:
                            try:
                                # Prepare old values for history (convert numpy types to Python native types)
                                def safe_int_convert(val):
                                    if pd.isna(val):
                                        return None
                                    try:
                                        # Clean the value before converting
                                        clean_val = str(val).replace('│', '').replace('|', '').strip()
                                        return int(float(clean_val))
                                    except:
                                        return None
                                
                                old_values = {
                                    '리드타임': safe_int_convert(products_df.iloc[idx]['리드타임']),
                                    '최소주문수량': safe_int_convert(products_df.iloc[idx]['최소주문수량']),
                                    '안전재고': safe_int_convert(products_df.iloc[idx]['안전재고']),
                                    '소비기한': products_df.iloc[idx]['소비기한'],
                                    # '제조사': products_df.iloc[idx].get('제조사', '')
                                }
                                
                                # 업데이트
                                rows_affected = ProductQueries.update_product(master_sku, **updates)
                                if rows_affected > 0:
                                    changes_made = True
                                    
                                    # Save history
                                    if 'user_info' in st.session_state:
                                        ProductQueries.save_update_history(
                                            master_sku,
                                            products_df.iloc[idx]['상품명'],
                                            old_values,
                                            updates,
                                            st.session_state.user_info['id'],
                                            st.session_state.user_info['name']
                                        )
                                else:
                                    errors.append(f"제품 {master_sku} 업데이트 실패")
                            except Exception as e:
                                errors.append(f"제품 {master_sku} 오류: {str(e)}")
                    
                    # Show results
                    if errors:
                        for error in errors:
                            st.error(error)
                    elif changes_made:
                        # Store success message in session state
                        st.session_state.product_update_message = "제품 정보가 성공적으로 업데이트되었습니다."
                        st.rerun()
                    else:
                        st.info("변경사항이 없습니다.")
                else:
                    st.error("행 추가/삭제는 지원되지 않습니다. 신규 제품은 '신규 제품 등록' 탭을 사용하세요.")
            except Exception as e:
                st.error(f"업데이트 중 오류 발생: {str(e)}")
    
    with tabs[1]:
        st.info("새로 등록할 제품의 정보를 입력하고 등록하세요.")
        
        col_single, col_set = st.columns(2)
        
        with col_single:
            st.subheader("신규 제품 등록 - 단품")
            
            # Get the latest playauto SKU and generate the next one
            latest_sku = ProductQueries.get_latest_playauto_sku()
            if latest_sku and latest_sku.startswith('PA-'):
                try:
                    # Extract the number part and increment
                    sku_number = int(latest_sku.split('-')[1])
                    next_sku = f"PA-{sku_number + 1:03d}"
                except:
                    next_sku = "PA-001"
            else:
                next_sku = "PA-001"
            
            # Display the auto-generated SKU
            
            with st.form("new_product_form"):
                master_sku = st.text_input("마스터 SKU*")
                product_name = st.text_input("상품명*")
                category = st.selectbox("카테고리", [
                    "영양제", "건강식품", "검사권", "커피", "건기식", "사무용품", "기타물품"
                ])

                col1, col2 = st.columns(2)
                with col1:
                    current_stock = st.number_input("현재재고", min_value=0, value=100)
                    safety_stock = st.number_input("안전재고", min_value=0, value=100)
                
                with col2:
                    lead_time = st.number_input("리드타임(일)", min_value=1, value=30)
                    moq = st.number_input("최소주문수량(MOQ)", min_value=0, value=100)
                
                supplier = st.selectbox("공급업체", [
                    "NPK", "다빈치랩", "바이오땡", 
                    "재화", "재화커뮤니케이션", "성원애드피아,재화", "성원애드피아", "지엠엠씨", "우림문구", "코스모라이프", "인터넷", 
                    "기타"
                ])
                expiration = st.date_input("소비기한")  # , value=datetime.now().date()

                if st.form_submit_button("제품 등록 (단품)"):
                    # Validate required fields
                    if not master_sku or not product_name:
                        st.error("필수 필드를 모두 입력해주세요.")
                    else:
                        try:
                            # Execute the insert using the ProductQueries class
                            rows_affected = ProductQueries.insert_product(
                                master_sku=master_sku,
                                playauto_sku=next_sku,
                                product_name=product_name,
                                category=category,
                                is_set='단품',
                                current_stock=current_stock,
                                lead_time=lead_time,
                                moq=moq,
                                safety_stock=safety_stock,
                                supplier=supplier,
                                expiration=expiration,
                                user_id=st.session_state.user_info['id'] if 'user_info' in st.session_state else '', 
                                user_name=st.session_state.user_info['name'] if 'user_info' in st.session_state else ''
                            )
                            
                            if rows_affected > 0:
                                # Store success message in session state
                                st.session_state.product_success_message = f"단품 제품 '{product_name}'이(가) 플레이오토 SKU '{next_sku}'로 성공적으로 등록되었습니다."
                                st.rerun()  # Refresh the page to show the new product
                            else:
                                st.error("제품 등록에 실패했습니다.")
                        except Exception as e:
                            st.error(f"데이터베이스 오류: {str(e)}")
                
        with col_set:
            st.subheader("신규 제품 등록 - 세트")
            
            # Get the latest playauto SKU and generate the next one
            latest_sku = ProductQueries.get_latest_playauto_sku()
            if latest_sku and latest_sku.startswith('PA-'):
                try:
                    # Extract the number part and increment
                    sku_number = int(latest_sku.split('-')[1])
                    next_sku = f"PA-{sku_number + 1:03d}"
                except:
                    next_sku = "PA-001"
            else:
                next_sku = "PA-001"
            
            with st.form("new_product_form_set"):
                master_sku = st.text_input("마스터 SKU*")
                product_name = st.text_input("상품명*")

                col_cat1, col_cat2, col_cat3 = st.columns(3)
                with col_cat1:
                    category = st.selectbox("카테고리", [
                        "영양제", "건강식품", "검사권", "커피", "건기식", "사무용품", "기타물품"
                    ])
                with col_cat2:
                    category_mid = st.selectbox("카테고리_중분류", [
                        "중금속", "알러지", "장내세균", "호르몬", 
                        "스트레스", "대사기능", "펫", "공통", 
                    ])
                with col_cat3:
                    category_low = st.text_input("카테고리_소분류")
                
                col1, col2 = st.columns(2)
                with col1:
                    current_stock = st.number_input("현재재고", min_value=0, value=100)
                    safety_stock = st.number_input("안전재고", min_value=0, value=100)
                with col2:
                    lead_time = st.number_input("리드타임(일)", min_value=1, value=30)
                    moq = st.number_input("최소주문수량(MOQ)", min_value=1, value=100)
                
                multiple = st.number_input("출고 배수", min_value=1, value=3, help="세트 상품의 출고 배수를 입력하세요 (1 이상)")
                
                supplier = st.selectbox("공급업체", [
                    "NPK", "다빈치랩", "바이오땡", 
                    "재화", "재화커뮤니케이션", "성원애드피아,재화", "성원애드피아", "지엠엠씨", "우림문구", "코스모라이프", "인터넷", 
                    "기타"
                ])
                expiration = st.date_input("소비기한")  # , value=datetime.now().date()

                if st.form_submit_button("제품 등록 (세트)"):
                    # Validate required fields
                    if not master_sku or not product_name:
                        st.error("필수 필드를 모두 입력해주세요.")
                    # Validate multiple for set products
                    elif multiple <= 0:
                        st.error("세트 상품의 출고 배수는 1 이상이어야 합니다.")
                    else:
                        try:
                            # Execute the insert using the ProductQueries class
                            rows_affected = ProductQueries.insert_product(
                                master_sku=master_sku,
                                playauto_sku=next_sku,
                                product_name=product_name,
                                category=category,
                                is_set='세트',
                                current_stock=current_stock,
                                lead_time=lead_time,
                                moq=moq,
                                safety_stock=safety_stock,
                                supplier=supplier,
                                expiration=expiration,
                                user_id=st.session_state.user_info['id'] if 'user_info' in st.session_state else ''
                            )
                            ProductQueries.set_product_info(  # rows_affected_category
                                master_sku=master_sku,
                                playauto_sku=next_sku,
                                product_name=product_name,
                                is_set='세트',
                                multiple=multiple, 
                                category=category,
                                category_mid=category_mid,  # 세트 상품은 카테고리_중분류 있음
                                category_low=category_low,
                            )
                            
                            if rows_affected > 0:
                                # Store success message in session state
                                st.session_state.product_success_message = f"세트 제품 '{product_name}'이(가) 플레이오토 SKU '{next_sku}'로 성공적으로 등록되었습니다. (출고 배수: {multiple})"
                                st.rerun()  # Refresh the page to show the new product
                            else:
                                st.error("제품 등록에 실패했습니다.")
                        except Exception as e:
                            st.error(f"데이터베이스 오류: {str(e)}")
        
        # Show success message at the bottom of the tab, outside of columns
        if 'product_success_message' in st.session_state:
            st.success(st.session_state.product_success_message)
            # del st.session_state.product_success_message
    
# Inventory Management page
def show_inventory():
    st.title("📦 재고 관리")
    
    tabs = st.tabs(["입출고 조정", "기존 입출고 내역 수정", "재고 조정"])
    
    with tabs[0]:
        st.subheader("입출고 조정하기")
        st.info("상품별 입출고 수량을 조정할 수 있는 페이지입니다. 아래 표에서 직접 편집하거나, 엑셀 파일을 업로드하여 일괄 처리할 수 있습니다.")
        st.warning("⚠️ 입력하신 입출고 양만큼 현재 재고 값이 변동됩니다.")
        
        # Section for direct editing
        st.subheader("✏️ 직접 편집")
        st.caption("아래 표에서 입고량과 출고량을 직접 입력한 후 저장 버튼을 클릭하세요.")
        st.info("📌 세트 상품의 경우: 출고량에 배수가 자동으로 적용됩니다. 예) 배수가 3인 세트 상품에 출고량 2를 입력하면 실제로 6개가 출고됩니다.")
        
        # Display success message if exists
        if 'inventory_success_message' in st.session_state:
            st.success(st.session_state.inventory_success_message)
            del st.session_state.inventory_success_message
        
        # Load product data from database for template
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                products_df = pd.DataFrame(products_data)
                inventory_df = pd.DataFrame({
                    '마스터 SKU': products_df['마스터_sku'],
                    '플레이오토 SKU': products_df['플레이오토_sku'],
                    '상품명': products_df['상품명'],
                    '카테고리': products_df['카테고리'],
                    '세트 유무': products_df['세트유무'],
                    '배수': products_df['배수'],
                    '현재 재고': products_df['현재재고'],
                    '입고량': [0] * len(products_df),
                    '출고량': [0] * len(products_df), 
                    '시점': [0] * len(products_df), 
                })
            else:
                # 샘플
                inventory_df = pd.DataFrame({
                    '마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                    '플레이오토 SKU': ['PA-001', 'PA-002', 'PA-003'],
                    '상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                    '카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                    '세트 유무': ['단품', '단품', '세트'],
                    '배수': [1, 1, 3],
                    '현재 재고': [150, 45, 200],
                    '입고량': [0, 0, 0],
                    '출고량': [0, 0, 0]
                })
        except:
            # 샘플
            inventory_df = pd.DataFrame({
                '마스터 SKU': ['VIT-C-1000', 'OMEGA-3-500', 'PROBIO-10B'],
                '플레이오토 SKU': ['PA-001', 'PA-002', 'PA-003'],
                '상품명': ['비타민C 1000mg', '오메가3 500mg', '프로바이오틱스 10B'],
                '카테고리': ['비타민', '오메가3', '프로바이오틱스'],
                '세트 유무': ['단품', '단품', '세트'],
                '배수': [1, 1, 3],
                '현재 재고': [150, 45, 200],
                '입고량': [0, 0, 0],
                '출고량': [0, 0, 0]
            })
        
        # st.dataframe(inventory_df, hide_index=True, use_container_width=True)
        edited_df = st.data_editor(
            inventory_df,
            use_container_width=True,
            num_rows="fixed",
            key="inventory_editor",
            disabled=['마스터 SKU', '플레이오토 SKU', '상품명', '카테고리', '세트 유무', '배수', '현재 재고']
        )

        # 입출고 날짜 및 시간 입력
        use_custom_datetime = st.checkbox("입출고 시점 직접 지정", value=False, help="체크하지 않으면 현재 시간이 자동으로 기록됩니다.")
        
        if use_custom_datetime:
            col_date, col_time = st.columns(2)
            with col_date:
                # Initialize session state only once
                if 'invinout_date' not in st.session_state:
                    st.session_state.invinout_date = datetime.now().date()
                invinout_date = st.date_input("입출고 날짜", key='invinout_date')
            with col_time:
                # Initialize session state only once
                if 'invinout_time' not in st.session_state:
                    st.session_state.invinout_time = datetime.now().time()
                invinout_time = st.time_input("입출고 시간", key='invinout_time')
            
            # Combine date and time into datetime object
            invinout_datetime = datetime.combine(invinout_date, invinout_time)
        else:
            # Use current datetime if checkbox is not checked
            invinout_datetime = datetime.now()

        if st.button("입출고량 수정사항 저장", type="primary"):
            try:
                if len(inventory_df) == len(edited_df):
                    changes_made = False
                    errors = []
                    success_count = 0
                    
                    for idx in range(len(inventory_df)):
                        # Get the master SKU (primary key)
                        master_sku = inventory_df.iloc[idx]['마스터 SKU']
                        is_set = inventory_df.iloc[idx]['세트 유무']
                        multiple = int(inventory_df.iloc[idx]['배수']) if pd.notna(inventory_df.iloc[idx]['배수']) else 0
                        
                        # Check if inventory changes were made
                        incoming_qty = int(edited_df.iloc[idx]['입고량'])
                        outgoing_qty = int(edited_df.iloc[idx]['출고량'])
                        
                        # Process incoming inventory if > 0
                        if incoming_qty > 0:
                            try:
                                result = ProductQueries.process_inventory_in(master_sku, incoming_qty)
                                if result > 0:
                                    # Record in shipment receipt table
                                    if 'user_info' in st.session_state:
                                        ShipmentQueries.insert_shipment_receipt(
                                            master_sku, '입고', incoming_qty, 
                                            st.session_state.user_info['id'],
                                            transaction_datetime=invinout_datetime
                                        )
                                    changes_made = True
                                    success_count += 1
                            except Exception as e:
                                errors.append(f"입고 처리 실패 - {master_sku}: {str(e)}")
                        
                        # Process outgoing inventory if > 0
                        if outgoing_qty > 0:
                            try:
                                # Apply multiple for 세트 products
                                actual_outgoing_qty = outgoing_qty
                                if is_set == '세트' and multiple > 0:
                                    actual_outgoing_qty = outgoing_qty * multiple
                                    
                                result = ProductQueries.process_inventory_out(master_sku, actual_outgoing_qty)
                                if result == 0:
                                    if is_set == '세트' and multiple > 0:
                                        errors.append(f"재고 부족 - {master_sku}: 세트 상품 출고량 {outgoing_qty} x 배수 {multiple} = {actual_outgoing_qty}개가 현재 재고보다 많습니다.")
                                    else:
                                        errors.append(f"재고 부족 - {master_sku}: 현재 재고보다 출고량이 많습니다.")
                                else:
                                    # Record in shipment receipt table with actual quantity
                                    if 'user_info' in st.session_state:
                                        ShipmentQueries.insert_shipment_receipt(
                                            master_sku, '출고', actual_outgoing_qty,
                                            st.session_state.user_info['id'],
                                            transaction_datetime=invinout_datetime
                                        )
                                    changes_made = True
                                    success_count += 1
                            except Exception as e:
                                errors.append(f"출고 처리 실패 - {master_sku}: {str(e)}")
                    
                    # Show results
                    if errors:
                        for error in errors:
                            st.error(error)
                    
                    if changes_made:
                        # Store success message in session state
                        st.session_state.inventory_success_message = f"✅ {success_count}개 항목의 입출고가 성공적으로 처리되었습니다."
                        st.rerun()
                    else:
                        st.info("변경된 입출고 수량이 없습니다.")
                            
            except Exception as e:
                st.error(f"업데이트 중 오류 발생: {str(e)}")
        else:
            # Use current datetime if checkbox is not checked
            invinout_datetime = datetime.now()

        # Add divider between direct edit and file upload sections
        st.divider()
        
        # Excel file upload section
        st.subheader("📤 엑셀 파일로 일괄 업로드")
        st.info("여러 제품의 입출고를 한번에 처리하려면 엑셀 템플릿을 다운로드하여 수정 후 업로드하세요.")
        
        # 엑셀로 변환
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            inventory_df.to_excel(writer, index=False, sheet_name='Sheet1')
        
        st.download_button(
            label="📥 템플릿 다운로드",
            data=buffer.getvalue(),
            file_name=f"inventory_template_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        uploaded_file = st.file_uploader(
            "재고 파일 업로드 (CSV, Excel)",
            type=['csv', 'xlsx', 'xls']
        )
        
        if uploaded_file is not None:
            # Read file
            try:
                if uploaded_file.name.endswith('.csv'):
                    try:
                        # Try UTF-8 first
                        df = pd.read_csv(uploaded_file, encoding='utf-8')
                    except UnicodeDecodeError:
                        # Try CP949 (Korean encoding)
                        uploaded_file.seek(0)
                        try:
                            df = pd.read_csv(uploaded_file, encoding='cp949')
                        except UnicodeDecodeError:
                            # Try EUC-KR
                            uploaded_file.seek(0)
                            df = pd.read_csv(uploaded_file, encoding='euc-kr')
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.dataframe(df, use_container_width=True)
                
                # Date and time selection for Excel upload
                use_custom_datetime_excel = st.checkbox("엑셀 업로드 입출고 시점 직접 지정", value=False, 
                                                       help="체크하지 않으면 현재 시간이 자동으로 기록됩니다.",
                                                       key="excel_datetime_checkbox")
                
                if use_custom_datetime_excel:
                    col_date_excel, col_time_excel = st.columns(2)
                    with col_date_excel:
                        excel_date = st.date_input("입출고 날짜", value=datetime.now().date(), key="excel_date")
                    with col_time_excel:
                        excel_time = st.time_input("입출고 시간", value=datetime.now().time(), key="excel_time")
                    
                    # Combine date and time into datetime object
                    excel_datetime = datetime.combine(excel_date, excel_time)
                else:
                    # Use current datetime if checkbox is not checked
                    excel_datetime = datetime.now()
                    
            except Exception as e:
                st.error(f"파일 읽기 오류: {str(e)}")
                st.info("CSV 파일의 경우 인코딩 문제가 있을 수 있습니다. Excel 파일(.xlsx)로 변환 후 업로드해주세요.")
                return
            
            # Initialize confirmation state if not exists
            if 'confirm_inventory_update' not in st.session_state:
                st.session_state.confirm_inventory_update = False
            
            col1, col2 = st.columns(2)
            with col1:  # 입출고 업데이트 진행
                if not st.session_state.confirm_inventory_update:
                    if st.button("✅ 재고 업데이트", use_container_width=True):
                        st.session_state.confirm_inventory_update = True
                        st.rerun()
                else:
                    st.warning("⚠️ 정말로 입출고량을 업데이트 하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
                    col1_1, col1_2 = st.columns(2)
                    with col1_1:
                        if st.button("✅ 확인", use_container_width=True):
                            try:
                                # 입출고 테이블에 데이터 올리기
                                success_count = 0
                                error_count = 0
                                errors = []
                                
                                for _, row in df.iterrows():
                                    try:
                                        # Extract data from row
                                        master_sku = str(row['마스터 SKU'])
                                        incoming_qty = int(row.get('입고량', 0))
                                        outgoing_qty = int(row.get('출고량', 0))
                                        is_set = row.get('세트 유무', '단품')
                                        multiple = int(row.get('배수', 0)) if pd.notna(row.get('배수', 0)) else 0
                                        
                                        # Process incoming inventory if exists
                                        if incoming_qty > 0:
                                            result = ProductQueries.process_inventory_in(master_sku, incoming_qty)
                                            if result > 0:
                                                # Record in shipment receipt table
                                                ShipmentQueries.insert_shipment_receipt(master_sku, '입고', incoming_qty, st.session_state.user_id, transaction_datetime=excel_datetime)
                                        
                                        # Process outgoing inventory if exists
                                        if outgoing_qty > 0:
                                            # Apply multiple for 세트 products
                                            actual_outgoing_qty = outgoing_qty
                                            if is_set == '세트' and multiple > 0:
                                                actual_outgoing_qty = outgoing_qty * multiple
                                                
                                            result = ProductQueries.process_inventory_out(master_sku, actual_outgoing_qty)
                                            if result == 0:
                                                if is_set == '세트' and multiple > 0:
                                                    errors.append(f"재고 부족: {master_sku} - 세트 상품 출고량 {outgoing_qty} x 배수 {multiple} = {actual_outgoing_qty}개가 현재 재고보다 많습니다.")
                                                else:
                                                    errors.append(f"재고 부족: {master_sku} (요청 수량: {actual_outgoing_qty})")
                                                error_count += 1
                                                continue
                                            else:
                                                # Record in shipment receipt table with actual quantity
                                                ShipmentQueries.insert_shipment_receipt(master_sku, '출고', actual_outgoing_qty, st.session_state.user_id, transaction_datetime=excel_datetime)
                                        
                                        if incoming_qty > 0 or outgoing_qty > 0:
                                            success_count += 1
                                        
                                    except Exception as e:
                                        errors.append(f"오류 발생 (SKU: {row.get('마스터 SKU', 'Unknown')}): {str(e)}")
                                        error_count += 1
                                
                                if success_count > 0:
                                    st.success(f"✅ 재고가 {success_count}개 성공적으로 업데이트되었습니다.")
                                    # Reset confirmation state after successful update
                                    st.session_state.confirm_inventory_update = False
                                
                                if error_count > 0:
                                    st.error(f"❌ {error_count}개 항목 처리 중 오류가 발생했습니다.")
                                    for error in errors:
                                        st.warning(error)
                                    # Reset confirmation state even on error
                                    st.session_state.confirm_inventory_update = False
                                        
                            except Exception as e:
                                st.error(f"처리 중 오류 발생: {str(e)}")
                                st.session_state.confirm_inventory_update = False
                    with col1_2:
                        if st.button("❌ 취소", use_container_width=True):
                            st.session_state.confirm_inventory_update = False
                            st.rerun()
            with col2:  # 입출고 업데이트 취소
                if not st.session_state.confirm_inventory_update:
                    if st.button("❌ 제고 업데이트 취소", use_container_width=True):
                        st.info("업로드가 취소되었습니다.")
    
    
    with tabs[1]:
        st.subheader("입출고 내역 수정하기")
        st.info("상품별 특정 시점의 입출고 수량 및 시간을 수정할 수 있습니다. 아래 표에서 수정하고 싶은 입고 혹은 출고 내역을 찾아 수정 요청 사항을 기입하세요.")
        st.warning("⚠️ 요청하신 수정 사항은 관리자의 승인에 따라 반영됩니다.")

        # Get all unique master SKUs and shipment types for filter options
        all_inv_data = ShipmentQueries.get_all_inv_inout()
        
        if all_inv_data:
            all_inv_df = pd.DataFrame(all_inv_data)
            
            st.write("### 📤 출고 내역")
            # Add search filters
            col1_out, col2_out = st.columns([1, 1])
            
            with col1_out:
                # Get unique product names
                # product_name_options = ['전체'] + sorted(all_inv_df['상품명'].unique().tolist())
                selected_product_out = st.text_input("상품명 검색 (출고)")
                
            with col2_out:
                selected_company_out = st.text_input("제조사 검색 (출고)")
            
            # Date range filter
            date_col1_out, date_col2_out = st.columns([1, 1])
            
            # Convert 시점 column to datetime for min/max calculation
            all_inv_df['시점'] = pd.to_datetime(all_inv_df['시점'])
            with date_col1_out:
                min_date_out = all_inv_df['시점'].min().date() if not all_inv_df.empty else datetime.now().date()
                start_date_out = st.date_input("시작일", value=min_date_out)
        
            with date_col2_out:
                max_date_out = all_inv_df['시점'].max().date() if not all_inv_df.empty else datetime.now().date()
                end_date_out = st.date_input("종료일", value=max_date_out)
            
            # Filter the data for 출고 (outgoing)
            filtered_data_out = all_inv_df[all_inv_df['입출고_여부'] == '출고'].copy()
            
            # Apply product name filter with partial matching for 출고
            if selected_product_out and selected_product_out.strip():
                filtered_data_out = filtered_data_out[filtered_data_out['상품명'].str.contains(selected_product_out, case=False, na=False)]
            # if selected_company_out and selected_company_out.strip():
            #     filtered_data_out = filtered_data_out[filtered_data_out['제조사'].str.contains(selected_company_out, case=False, na=False)]
            
            # Apply date range filter for 출고
            start_datetime_out = pd.Timestamp.combine(start_date_out, pd.Timestamp.min.time())
            end_datetime_out = pd.Timestamp.combine(end_date_out, pd.Timestamp.max.time())
            filtered_data_out = filtered_data_out[(filtered_data_out['시점'] >= start_datetime_out) & (filtered_data_out['시점'] <= end_datetime_out)]
            
            outgoing_data = filtered_data_out
            
            # Display 출고 (Outgoing) table
            if not outgoing_data.empty:
                outgoing_df = pd.DataFrame({
                    'inv_code': outgoing_data['inv_code'],
                    '마스터 SKU': outgoing_data['마스터_sku'], 
                    '상품명': outgoing_data['상품명'],
                    '제조사': outgoing_data['제조사'],
                    '수량': outgoing_data['수량'], 
                    '출고 시점': outgoing_data['시점'], 
                    '작업자 ID': outgoing_data['작업자_id'], 
                })
                
                st.session_state['original_outgoing_df'] = outgoing_df.copy()
                
                edited_outgoing_df = st.data_editor(
                    outgoing_df,
                    use_container_width=True,
                    num_rows="fixed",
                    key="outgoing_editor", 
                    disabled=['inv_code', '마스터 SKU', '상품명', '제조사',  '작업자 ID'],
                    # hide_index=True,
                    column_config={
                        'inv_code': None,
                        '출고 시점': st.column_config.DatetimeColumn(
                            '출고 시점',
                            format='YYYY-MM-DD HH:mm'
                        )
                    }
                )
                
                edit_reason_out = st.text_area("수정 사유 (출고)", key="out_reason")
                
                if st.button("📤 출고 수정 요청 저장", key="save_out"):
                    if edit_reason_out:
                        changes = []
                        for idx in range(len(outgoing_df)):
                            if (st.session_state['original_outgoing_df'].iloc[idx]['수량'] != edited_outgoing_df.iloc[idx]['수량'] or 
                                st.session_state['original_outgoing_df'].iloc[idx]['출고 시점'] != edited_outgoing_df.iloc[idx]['출고 시점']):
                                changes.append(idx)
                        
                        if changes:
                            success_count = 0
                            for idx in changes:
                                try:
                                    # Convert timestamps to datetime strings
                                    old_date = st.session_state['original_outgoing_df'].iloc[idx]['출고 시점']
                                    new_date = edited_outgoing_df.iloc[idx]['출고 시점']
                                    
                                    # Convert to datetime string format if needed
                                    if isinstance(old_date, (int, float)):
                                        # If it's a timestamp in milliseconds
                                        if old_date > 1e10:
                                            old_date = pd.Timestamp(old_date, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                                        else:
                                            old_date = pd.Timestamp(old_date, unit='s').strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, pd.Timestamp):
                                        old_date = old_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, datetime):
                                        old_date = old_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, str):
                                        # Already a string, just pass it through
                                        pass
                                    else:
                                        # Try to convert whatever it is
                                        old_date = str(old_date)
                                    
                                    if isinstance(new_date, (int, float)):
                                        # If it's a timestamp in milliseconds
                                        if new_date > 1e10:
                                            new_date = pd.Timestamp(new_date, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                                        else:
                                            new_date = pd.Timestamp(new_date, unit='s').strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, pd.Timestamp):
                                        new_date = new_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, datetime):
                                        new_date = new_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, str):
                                        # Already a string, just pass it through
                                        pass
                                    else:
                                        # Try to convert whatever it is
                                        new_date = str(new_date)
                                    
                                    ShipmentQueries.insert_edit_request(
                                        edited_outgoing_df.iloc[idx]['inv_code'],
                                        edited_outgoing_df.iloc[idx]['마스터 SKU'],
                                        edited_outgoing_df.iloc[idx]['상품명'],
                                        edited_outgoing_df.iloc[idx]['제조사'],
                                        '출고',
                                        int(st.session_state['original_outgoing_df'].iloc[idx]['수량']),
                                        int(edited_outgoing_df.iloc[idx]['수량']),
                                        old_date,
                                        new_date,
                                        st.session_state.user_info['name'] if 'user_info' in st.session_state else '',
                                        st.session_state.user_info['id'] if 'user_info' in st.session_state else '',
                                        edit_reason_out
                                    )
                                    success_count += 1
                                except Exception as e:
                                    st.error(f"오류: {str(e)}")
                            
                            if success_count > 0:
                                st.success(f"✅ {success_count}개의 출고 수정 요청이 저장되었습니다.")
                                st.rerun()
                        else:
                            st.warning("변경된 내용이 없습니다.")
                    else:
                        st.error("수정 사유를 입력해주세요.")
            else:
                st.info("📌 검색 조건에 맞는 출고 내역이 없습니다.")
            
            st.markdown("---")
            
            st.write("### 📥 입고 내역")
            
            # Add search filters
            col1_in, col2_in = st.columns([1, 1])
            
            with col1_in:
                # Get unique product names
                # product_name_options = ['전체'] + sorted(all_inv_df['상품명'].unique().tolist())
                selected_product_in = st.text_input("상품명 검색 (입고)")
                
            with col2_in:
                selected_company_in = st.text_input("제조사 검색 (입고)")
            
            # Date range filter
            date_col1_in, date_col2_in = st.columns([1, 1])
            
            # Convert 시점 column to datetime for min/max calculation
            all_inv_df['시점'] = pd.to_datetime(all_inv_df['시점'])
            with date_col1_in:
                min_date_in = all_inv_df['시점'].min().date() if not all_inv_df.empty else datetime.now().date()
                start_date_in = st.date_input("입고 시작일", value=min_date_in)
        
            with date_col2_in:
                max_date_in = all_inv_df['시점'].max().date() if not all_inv_df.empty else datetime.now().date()
                end_date_in = st.date_input("입고 종료일", value=max_date_in)
            
            # Filter the data for 입고 (incoming)
            filtered_data_in = all_inv_df[all_inv_df['입출고_여부'] == '입고'].copy()
            
            # Apply product name filter with partial matching for 입고
            if selected_product_in and selected_product_in.strip():
                filtered_data_in = filtered_data_in[filtered_data_in['상품명'].str.contains(selected_product_in, case=False, na=False)]
            
            # Apply date range filter for 입고
            start_datetime_in = pd.Timestamp.combine(start_date_in, pd.Timestamp.min.time())
            end_datetime_in = pd.Timestamp.combine(end_date_in, pd.Timestamp.max.time())
            filtered_data_in = filtered_data_in[(filtered_data_in['시점'] >= start_datetime_in) & (filtered_data_in['시점'] <= end_datetime_in)]
            
            incoming_data = filtered_data_in
            
            # Display 입고 (Incoming) table
            if not incoming_data.empty:
                incoming_df = pd.DataFrame({
                    'inv_code': incoming_data['inv_code'],
                    '마스터 SKU': incoming_data['마스터_sku'], 
                    '상품명': incoming_data['상품명'],
                    '제조사': incoming_data['제조사'],
                    '수량': incoming_data['수량'], 
                    '입고 시점': incoming_data['시점'], 
                    '작업자 ID': incoming_data['작업자_id'], 
                })
                
                st.session_state['original_incoming_df'] = incoming_df.copy()
                
                edited_incoming_df = st.data_editor(
                    incoming_df,
                    use_container_width=True,
                    num_rows="fixed",
                    key="incoming_editor", 
                    disabled=['inv_code', '마스터 SKU', '상품명', '제조사', '작업자 ID'],
                    # hide_index=True,
                    column_config={
                        'inv_code': None,
                        '입고 시점': st.column_config.DatetimeColumn(
                            '입고 시점',
                            format='YYYY-MM-DD HH:mm'
                        )
                    }
                )
                
                edit_reason_in = st.text_area("수정 사유 (입고)", key="in_reason")
                
                if st.button("📥 입고 수정 요청 저장", key="save_in"):
                    if edit_reason_in:
                        changes = []
                        for idx in range(len(incoming_df)):
                            if (st.session_state['original_incoming_df'].iloc[idx]['수량'] != edited_incoming_df.iloc[idx]['수량'] or 
                                st.session_state['original_incoming_df'].iloc[idx]['입고 시점'] != edited_incoming_df.iloc[idx]['입고 시점']):
                                changes.append(idx)
                        
                        if changes:
                            success_count = 0
                            for idx in changes:
                                try:
                                    # Convert timestamps to datetime strings
                                    old_date = st.session_state['original_incoming_df'].iloc[idx]['입고 시점']
                                    new_date = edited_incoming_df.iloc[idx]['입고 시점']
                                    
                                    # Convert to datetime string format if needed
                                    if isinstance(old_date, (int, float)):
                                        # If it's a timestamp in milliseconds
                                        if old_date > 1e10:
                                            old_date = pd.Timestamp(old_date, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                                        else:
                                            old_date = pd.Timestamp(old_date, unit='s').strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, pd.Timestamp):
                                        old_date = old_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, datetime):
                                        old_date = old_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(old_date, str):
                                        # Already a string, just pass it through
                                        pass
                                    else:
                                        # Try to convert whatever it is
                                        old_date = str(old_date)
                                    
                                    if isinstance(new_date, (int, float)):
                                        # If it's a timestamp in milliseconds
                                        if new_date > 1e10:
                                            new_date = pd.Timestamp(new_date, unit='ms').strftime('%Y-%m-%d %H:%M:%S')
                                        else:
                                            new_date = pd.Timestamp(new_date, unit='s').strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, pd.Timestamp):
                                        new_date = new_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, datetime):
                                        new_date = new_date.strftime('%Y-%m-%d %H:%M:%S')
                                    elif isinstance(new_date, str):
                                        # Already a string, just pass it through
                                        pass
                                    else:
                                        # Try to convert whatever it is
                                        new_date = str(new_date)

                                    ShipmentQueries.insert_edit_request(
                                        edited_incoming_df.iloc[idx]['inv_code'],
                                        edited_incoming_df.iloc[idx]['마스터 SKU'],
                                        edited_incoming_df.iloc[idx]['상품명'],
                                        edited_incoming_df.iloc[idx]['제조사'],
                                        '입고',
                                        int(st.session_state['original_incoming_df'].iloc[idx]['수량']),
                                        int(edited_incoming_df.iloc[idx]['수량']),
                                        old_date,
                                        new_date,
                                        st.session_state.user_info['name'] if 'user_info' in st.session_state else '',
                                        st.session_state.user_info['id'] if 'user_info' in st.session_state else '',
                                        edit_reason_in
                                    )
                                    success_count += 1
                                except Exception as e:
                                    st.error(f"오류: {str(e)}")
                            
                            if success_count > 0:
                                st.success(f"✅ {success_count}개의 입고 수정 요청이 저장되었습니다.")
                                st.rerun()
                        else:
                            st.warning("변경된 내용이 없습니다.")
                    else:
                        st.error("수정 사유를 입력해주세요.")
            else:
                st.info("📌 검색 조건에 맞는 입고 내역이 없습니다.")
        else:
            # No data at all
            st.info("📌 입출고 내역이 없습니다.")
        
    
    with tabs[2]:
        st.subheader("재고 조정")
        st.info("실제 재고와 시스템 재고가 다를 경우 조정할 수 있습니다.")
        
        # Show success message if exists
        if 'inventory_adjust_message' in st.session_state:
            st.success(st.session_state.inventory_adjust_message)
            if 'inventory_adjust_details' in st.session_state:
                st.info(st.session_state.inventory_adjust_details)
            del st.session_state.inventory_adjust_message
            if 'inventory_adjust_details' in st.session_state:
                del st.session_state.inventory_adjust_details
        
        # Get products from database
        products_dict = {}  # Store product name -> data mapping
        products_list = []
        current_stock = 0
        master_sku = None
        
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                for p in products_data:
                    products_list.append(p['상품명'])
                    products_dict[p['상품명']] = {
                        'master_sku': p['마스터_sku'],
                        'current_stock': p['현재재고']
                    }
        except:
            products_list = ["데이터 로드 오류"]
        
        product = st.selectbox(
            "제품 선택",
            products_list
        )
        
        # Get current stock for selected product
        if product in products_dict:
            current_stock = products_dict[product]['current_stock'] if products_dict[product]['current_stock'] is not None else 0
            master_sku = products_dict[product]['master_sku']
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("현재 시스템 재고", f"{current_stock}개")
        with col2:
            actual_stock = st.number_input("실제 재고", min_value=0, value=current_stock)
        
        reason = st.text_area("조정 사유")
        
        if st.button("재고 조정", use_container_width=True):
            if master_sku:  # if master_sku and reason.strip(): # 조정 사유가 포함되도록
                try:
                    # Update inventory
                    result = ProductQueries.adjust_inventory(master_sku, actual_stock)
                    
                    if result > 0:
                        # Save adjustment history
                        history_result = ProductQueries.adjust_history(master_sku, current_stock, actual_stock, reason, st.session_state.user_info['name'], st.session_state.user_id)
                        
                        # Record adjustment in shipment receipt if there's a difference
                        adjustment = actual_stock - current_stock
                        if adjustment != 0:
                            transaction_type = '입고' if adjustment > 0 else '출고'
                            ShipmentQueries.insert_shipment_receipt(
                                master_sku, 
                                transaction_type,  # Just use '입고' or '출고'
                                abs(adjustment), 
                                st.session_state.user_id
                            )
                        
                        # Store adjustment details if there's a difference
                        if adjustment != 0:
                            st.session_state.inventory_adjust_details = f"조정 내역: {current_stock}개 → {actual_stock}개 (차이: {adjustment:+d}개)"
                        
                        # Store success message in session state
                        st.session_state.inventory_adjust_message = f"{product}의 재고가 {actual_stock}개로 조정되었습니다."
                        
                        st.rerun()  # Refresh to show updated stock
                    else:
                        st.error("재고 조정에 실패했습니다.")
                except Exception as e:
                    st.error(f"오류 발생: {str(e)}")
            # elif not reason.strip():
            #     st.warning("조정 사유를 입력해주세요.")
            else:
                st.error("제품 정보를 찾을 수 없습니다.")

# Prediction page
def show_prediction():
    st.title("🔮 수요 예측")
    
    tabs = st.tabs(["예측 결과 확인", "예측 결과 수동 조정"])
    
    with tabs[0]:
        st.subheader("AI 기반 수요 예측")
        
        models_loaded = False
        future_predictions = {}
        model_results = {}
        
        # First try to load improved adaptive models
        try:
            with open('./models/future_predictions.pkl', 'rb') as f:
                future_predictions = pickle.load(f)
            with open('./models/model_results.pkl', 'rb') as f:
                model_results = pickle.load(f)
            models_loaded = True
            
            # Check for products with insufficient data
            insufficient_data_products = []
            for sku, pred in future_predictions.items():
                if pred.get('method') == 'baseline_insufficient_data' or pred.get('confidence') == 'very_low':
                    # Find product name for this SKU
                    for prod_name, sku_code in {
                        '바이오밸런스': 'BIOBAL',
                        '풍성밸런스': 'PSBAL',  # AMPLEBAL
                        '클린밸런스': 'CLBAL',  # CLEANBAL
                        '뉴로마스터': 'NEUROMASTER',
                        '키네코어': 'KNCORE',  # KINECORE
                        '다래 케어': 'DARAECARE',
                        '선화이버': 'SF',  # SUNFIBER
                        '영데이즈': 'YOUNGDAYS',
                        '당당케어': 'DDCARE',
                        '칸디다웨이': 'KDDWAY',
                        '퓨어마그 펫': 'PMPKOR'
                    }.items():
                        if sku_code == sku:
                            data_points = pred.get('category_info', {}).get('data_points', 'N/A')
                            insufficient_data_products.append(f"{prod_name} ({data_points}개월)")
                            break
            
            if insufficient_data_products:
                with st.expander("⚠️ 데이터 부족 제품 목록", expanded=False):
                    st.warning(f"""
                    다음 제품들은 충분한 과거 데이터가 없어 정확한 예측이 제한됩니다:
                    
                    {', '.join(insufficient_data_products)}
                    
                    **최소 4개월**의 데이터가 필요하며, 현재는 단순 평균 기반 추정치를 제공합니다.
                    """)
        except Exception as e:
            st.error(f"모델 로드 오류: {str(e)}")
            st.info("학습된 모델이 없습니다.")
            models_loaded = False
        
        sku_mapping = {
            '바이오밸런스': 'BIOBAL',
            '풍성밸런스': 'PSBAL',  # AMPLEBAL
            '클린밸런스': 'CLBAL',  # CLEANBAL
            '뉴로마스터': 'NEUROMASTER',
            '키네코어': 'KNCORE',  # KINECORE
            '다래 케어': 'DARAECARE',
            '선화이버': 'SF',  # SUNFIBER
            '영데이즈': 'YOUNGDAYS',
            '당당케어': 'DDCARE',
            '칸디다웨이': 'KDDWAY',
            '퓨어마그 펫': 'PMPKOR'
        }
        
        # 예측 결과 조회할 제품 선택하기
        try:
            products_data = ProductQueries.get_all_products()
            if products_data:
                products_list = [p['상품명'] for p in products_data]
        except:
            pass
        
        product = st.selectbox("제품 선택", products_list)
        
        selected_sku = sku_mapping.get(product, None)

        current_date = datetime.now()
        
        # 이번 달과 향후 3개월에 대한 예측
        st.info("이번 달과 향후 3개월에 대한 예측을 표시합니다.")  # st.info(f"향후 3개월({prediction_months[0]}, {prediction_months[1]}, {prediction_months[2]}) 예측을 표시합니다.")
        period_days = 90  # 3개월
        
        # 예측 결과 확인
        if models_loaded and selected_sku:
            # First check if this SKU has any predictions at all
            if selected_sku not in future_predictions:
                # No predictions available for this product
                st.error(f"""
                ❌ **예측 불가**
                
                {product}는 충분한 데이터가 없어 예측을 제공할 수 없습니다.
                
                **이유**: 예측 모델 학습을 위해서는 최소 5개월의 과거 데이터가 필요합니다.
                
                **해결 방법**: 
                - 더 많은 데이터가 축적될 때까지 기다려주세요
                - 현재는 과거 평균값이나 수동 입력을 사용하세요
                """)
                
                # Show historical data if available
                try:
                    all_shipments = ShipmentQueries.get_all_inv_out()
                    if all_shipments:
                        df_shipments = pd.DataFrame(all_shipments)
                        df_shipments['시점'] = pd.to_datetime(df_shipments['시점'])
                        df_sku = df_shipments[df_shipments['마스터_sku'] == selected_sku]
                        
                        if not df_sku.empty:
                            st.subheader("📊 과거 데이터")
                            
                            # Group by month
                            df_sku['연월'] = df_sku['시점'].dt.to_period('M')
                            monthly_summary = df_sku.groupby('연월')['수량'].sum().reset_index()
                            monthly_summary['연월'] = monthly_summary['연월'].astype(str)
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("총 데이터 기간", f"{len(monthly_summary)}개월")
                            with col2:
                                avg_monthly = monthly_summary['수량'].mean()
                                st.metric("월평균 출고량", f"{int(avg_monthly):,}개")
                            
                            # Show monthly data
                            st.dataframe(
                                monthly_summary.rename(columns={'연월': '월', '수량': '출고량'}),
                                use_container_width=True,
                                hide_index=True
                            )
                            
                            st.info("💡 최소 5개월의 데이터가 축적되면 자동으로 예측이 활성화됩니다.")
                except:
                    pass
            elif selected_sku in future_predictions:
                # Check if using improved model structure (monthly predictions)
                if 'forecast_months' in future_predictions.get(selected_sku, {}):
                    predictions = future_predictions[selected_sku]
                    updated_prediction = PredictionQueries.get_adjusted_prediction(selected_sku)  # 조정한 예측 값이 있으면 불러오기
                
                # Check for insufficient data warning
                if predictions:
                    # Check if this is a baseline model due to insufficient data
                    method = predictions.get('method', '')
                    confidence = predictions.get('confidence', '')
                    
                    if method == 'baseline_insufficient_data' or confidence == 'very_low':
                        st.warning(f"""
                        ⚠️ **데이터 부족 경고**
                        
                        {product}는 충분한 과거 데이터가 없어 정확한 예측이 어렵습니다.
                        - 현재 이용 가능한 데이터: {predictions.get('category_info', {}).get('data_points', 'N/A')}개월
                        - 최소 필요 데이터: 5개월
                        - 예측 방법: 단순 평균 기반 추정
                        
                        **주의**: 아래 예측값은 참고용이며, 실제와 크게 다를 수 있습니다.
                        """)
                    elif confidence == 'low' or confidence == 'low-medium':
                        st.info(f"""
                        ℹ️ **제한된 데이터**
                        
                        {product}의 예측 신뢰도가 낮습니다.
                        - 신뢰도: {confidence}
                        - 더 많은 데이터가 축적되면 예측 정확도가 향상됩니다.
                        """)
                
                if predictions:
                    # Get predictions - check for adaptive model structure first
                    if 'predictions' in predictions:
                        # Adaptive model structure - should have 4 values: Aug, Sep, Oct, Nov
                        forecast_values = predictions.get('predictions', [])
                        # Also store August prediction separately if available
                        if 'august_full_prediction' in predictions:
                            august_full_pred = predictions.get('august_full_prediction', None)
                    else:
                        # Old model structure - ARIMA predictions
                        forecast_values = predictions.get('arima', [])
                        august_full_pred = None

                    # Check if we have adjusted predictions and use them instead
                    if updated_prediction and len(updated_prediction) > 0:
                        adj_values = updated_prediction[0]
                        if (adj_values['adjusted_1month'] is not None and
                            adj_values['adjusted_2month'] is not None and
                            adj_values['adjusted_3month'] is not None):
                            forecast_values = [
                                float(adj_values['adjusted_1month']),
                                float(adj_values['adjusted_2month']),
                                float(adj_values['adjusted_3month'])
                            ]
                    
                    if len(forecast_values) > 0:
                        # Calculate total predicted shipment
                        total_forecast = np.sum(forecast_values)
                    
                    # Get model performance metrics if available
                    rmse = None
                    mae = None
                    mape = None
                    if 'forecast_months' in predictions:
                        # Check for improved model structure with direct metrics
                        if selected_sku in model_results:
                            # Direct access to metrics from improved model
                            rmse = model_results[selected_sku].get('rmse', None)
                            mae = model_results[selected_sku].get('mae', None)
                            
                            # Legacy structure check
                            if rmse is None:
                                if 'adaptive' in model_results.get(selected_sku, {}):
                                    # Adaptive model structure
                                    metrics = model_results[selected_sku]['adaptive'].get('metrics', {})
                                    rmse = metrics.get('RMSE', None)
                                    mape = metrics.get('MAPE', None)
                                elif 'arima' in model_results.get(selected_sku, {}):
                                    # Old improved model structure
                                    metrics = model_results[selected_sku]['arima'].get('metrics', {})
                                    rmse = metrics.get('RMSE', None)
                                    mape = metrics.get('MAPE', None)
                    else:
                        # Old model structure
                        if selected_sku in model_results and period_days in model_results[selected_sku]:
                            metrics = model_results[selected_sku][period_days].get('arima', {}).get('metrics', {})
                            rmse = metrics.get('RMSE', None)
                            mape = metrics.get('MAPE', None)
                    
                    # Get product info from database
                    moq = 100  # default
                    safety_stock = 100  # default
                    try:
                        products_data = ProductQueries.get_all_products()
                        for p in products_data:
                            if p['상품명'] == product:
                                moq = p['최소주문수량']
                                safety_stock = p['안전재고']
                                break
                    except:
                        pass
                    
                    # Calculate recommended order quantity
                    recommended_order = max(int(total_forecast + safety_stock), moq)
                    recommended_order = ((recommended_order + moq - 1) // moq) * moq  # Round up to MOQ
                    
                    # Add confidence indicator to metrics
                    confidence_level = predictions.get('confidence', 'unknown')
                    confidence_emoji = {
                        'very_low': '⚠️',
                        'low': '⚠️',
                        'low-medium': '⚠️',
                        'medium': '✓',
                        'medium-high': '✓✓',
                        'high': '✓✓✓'
                    }.get(confidence_level, '?')
                    
                    # Prediction chart with historical data
                    st.subheader("예측 차트")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("총 예측 값", f"{int(total_forecast):,}개", f"월평균 {int(total_forecast / 4):,}개", help="이번달 + 다음 3개월 예측값")
                    with col2:
                        if mae is not None and rmse is not None:
                            # Get historical average for context
                            historical_avg = None
                            try:
                                # Get historical shipment data for this SKU
                                all_shipments = ShipmentQueries.get_all_inv_out()
                                if all_shipments:
                                    # Use column indices instead of names to avoid encoding issues
                                    df_hist = pd.DataFrame(all_shipments)
                                    # Column 0: 마스터_SKU, Column 1: 수량, Column 2: 시점
                                    df_hist.columns = ['마스터_SKU', '수량', '시점']
                                    df_sku = df_hist[df_hist['마스터_SKU'] == selected_sku].copy()
                                    if not df_sku.empty:
                                        df_sku['시점'] = pd.to_datetime(df_sku['시점'])
                                        df_sku['연월'] = df_sku['시점'].dt.to_period('M')
                                        monthly_hist = df_sku.groupby('연월')['수량'].sum()
                                        if len(monthly_hist) > 0:
                                            historical_avg = monthly_hist.mean()
                            except Exception as e:
                                # Debug: print error to console
                                print(f"Error getting historical data for {selected_sku}: {e}")
                            
                            # Calculate normalized error (percentage)
                            if historical_avg and historical_avg > 0:
                                mae_percentage = (mae / historical_avg) * 100
                                rmse_percentage = (rmse / historical_avg) * 100
                                
                                # Performance categories based on MAE percentage
                                if mae_percentage < 20:
                                    performance = "매우 우수 ⭐"
                                elif mae_percentage < 30:
                                    performance = "우수 👍"
                                elif mae_percentage < 40:
                                    performance = "양호 🙂"
                                elif mae_percentage < 50:
                                    performance = "보통 😐"
                                else:
                                    performance = "개선필요 ⚠️"
                                
                                # Display normalized metrics with context
                                st.metric("예측 오차율", 
                                        #  f"{100 - mae_percentage:.1f}%",
                                         f"{mae_percentage:.1f}%", help="MAE 오차"
                                )
                                st.caption(f"평균 {mae:.0f}개 오차 (월 평균 {historical_avg:.0f}개 대비)")
                                st.caption(f"성능: {performance}")
                            else:
                                st.caption("과거 데이터 부족으로 상대 정확도 계산 불가")
                        elif rmse is not None:
                            # Fallback to RMSE only if MAE not available
                            avg_monthly = total_forecast / 3 if total_forecast > 0 else 1
                            rmse_ratio = rmse / avg_monthly if avg_monthly > 0 else 1
                            
                            if rmse_ratio < 0.3:
                                performance = "훌륭 👍"
                            elif rmse_ratio < 0.5:
                                performance = "양호 🙂"
                            elif rmse_ratio < 0.8:
                                performance = "보통 😐"
                            else:
                                performance = "개선필요 ⚠️"
                            
                            st.metric("모델 정확도", f"RMSE: {rmse:.1f}")
                            st.caption(f"성능: {performance}")
                        else:
                            # Show confidence level instead of accuracy when no metrics available
                            confidence_display = {
                                'very_low': '매우 낮음 ⚠️',
                                'low': '낮음 ⚠️',
                                'low-medium': '중하 ⚠️',
                                'medium': '보통 ✓',
                                'medium-high': '중상 ✓✓',
                                'high': '높음 ✓✓✓'
                            }.get(confidence_level, '알 수 없음')
                            
                            st.metric("예측 신뢰도", confidence_display)
                            
                            # Show data availability info
                            if 'category_info' in predictions:
                                data_points = predictions['category_info'].get('data_points', 'N/A')
                                st.caption(f"학습 데이터: {data_points}개월")
                    
                    # Get current date first
                    current_date = datetime.now()
                    current_year = current_date.year
                    current_month = current_date.month
                    
                    # Initialize variables outside try block
                    historical_months = []
                    current_month_actual = 0  # Store current month actual
                    
                    # 출고량 데이터 불러오기
                    try:
                        all_shipments = ShipmentQueries.get_all_inv_out()
                        if all_shipments:
                            df_shipments = pd.DataFrame(all_shipments)
                            df_shipments['시점'] = pd.to_datetime(df_shipments['시점'])
                            
                            df_sku = df_shipments[df_shipments['마스터_sku'] == selected_sku].copy()
                            
                            if not df_sku.empty:
                                # 지난 6개월
                                for i in range(5, 0, -1):  # 5 months ago to 1 month ago
                                    target_date = current_date - relativedelta(months=i)
                                    year = target_date.year
                                    month = target_date.month
                                    
                                    # Filter data for this month
                                    month_data = df_sku[
                                        (df_sku['시점'].dt.year == year) & 
                                        (df_sku['시점'].dt.month == month)
                                    ]
                                    
                                    # Sum the quantities for this month
                                    month_total = month_data['수량'].sum() if not month_data.empty else 0
                                    
                                    historical_months.append({
                                        'date': pd.Timestamp(year, month, 1),
                                        'value': float(month_total)
                                    })
                                
                                # 현재 달의 실제 값
                                current_month_data = df_sku[
                                    (df_sku['시점'].dt.year == current_year) & 
                                    (df_sku['시점'].dt.month == current_month)
                                ]
                                current_month_actual = current_month_data['수량'].sum() if not current_month_data.empty else 0
                    except Exception as e:
                        st.warning(f"과거 데이터 로드 중 오류: {str(e)}")
                    
                    # Create date range for predictions (current month + next 3 months)
                    if 'forecast_months' in predictions:
                        # Check if this is the improved model with full month predictions
                        forecast_months = predictions.get('forecast_months', [])
                        
                        # Check for the new model structure with august_full_prediction
                        if 'august_full_prediction' in predictions:
                            # New improved model: includes full August prediction
                            prediction_dates = []
                            # Add current month (August)
                            prediction_dates.append(pd.Timestamp(current_year, current_month, 1))
                            # Add next 3 months
                            for i in range(1, 4):  # September, October, November
                                future_date = current_date + relativedelta(months=i)
                                prediction_dates.append(pd.Timestamp(future_date.year, future_date.month, 1))
                            
                            # Get August full prediction and next 3 months
                            august_pred = predictions.get('august_full_prediction', 0)
                            if len(forecast_values) >= 4:
                                # forecast_values[0] is august_full, [1] is sep, [2] is oct, [3] is nov
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates,
                                    '출고량': [forecast_values[0], forecast_values[1], forecast_values[2], forecast_values[3]]
                                })
                            else:
                                # Fallback
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates,
                                    '출고량': [august_pred] + list(forecast_values[:3])
                                })
                        elif 'august_remainder' in forecast_months or 'august_remainder' in str(forecast_months):
                            # Older improved model: has August, Sep, Oct, Nov
                            # Even though it says "august_remainder", the first value is the full August prediction
                            prediction_dates = []
                            # Add current month (August)
                            prediction_dates.append(pd.Timestamp(current_year, current_month, 1))
                            # Add next 3 months
                            for i in range(1, 4):  # September, October, November
                                future_date = current_date + relativedelta(months=i)
                                prediction_dates.append(pd.Timestamp(future_date.year, future_date.month, 1))
                            
                            if len(forecast_values) >= 4:
                                # All 4 months including August
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates,
                                    '출고량': forecast_values[:4]  # August, Sep, Oct, Nov
                                })
                            else:
                                # Fallback if not enough values
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates[:len(forecast_values)],
                                    '출고량': forecast_values
                                })
                        else:
                            # Regular model: Check if first month is current month
                            prediction_dates = []
                            # Always include current month for comparison
                            prediction_dates.append(pd.Timestamp(current_year, current_month, 1))
                            for i in range(1, 4):  # Next 3 months
                                future_date = current_date + relativedelta(months=i)
                                prediction_dates.append(pd.Timestamp(future_date.year, future_date.month, 1))
                            
                            # If we have 4 values, use all. Otherwise pad with zeros for current month
                            if len(forecast_values) >= 4:
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates,
                                    '출고량': forecast_values[:4]
                                })
                            else:
                                # Assume first value is for next month, add 0 for current month
                                monthly_pred = pd.DataFrame({
                                    '날짜': prediction_dates,
                                    '출고량': [0] + list(forecast_values[:3])  # 0 for August, then predictions
                                })
                    else:
                        # Old model - weekly predictions need conversion
                        last_date = predictions.get('last_date', datetime.now())
                        if isinstance(last_date, str):
                            last_date = pd.to_datetime(last_date)
                        
                        # For weekly predictions, create weekly dates
                        prediction_dates = pd.date_range(
                            start=last_date + pd.Timedelta(days=7),
                            periods=len(forecast_values),
                            freq='W'
                        )
                        
                        # Create weekly prediction dataframe
                        weekly_pred_df = pd.DataFrame({
                            '날짜': prediction_dates,
                            '출고량': forecast_values
                        })
                        
                        # Convert predictions to monthly
                        weekly_pred_df['월'] = weekly_pred_df['날짜'].dt.to_period('M')
                        monthly_pred = weekly_pred_df.groupby('월')['출고량'].sum().reset_index()
                        monthly_pred['날짜'] = monthly_pred['월'].apply(lambda x: x.to_timestamp())
                        
                        # Always show 3 months
                        monthly_pred = monthly_pred.head(3)
                    
                    # Prepare data for chart
                    # Historical data (excluding current month)
                    hist_labels = []
                    hist_values = []
                    for month in historical_months:
                        period = pd.Timestamp(month['date']).to_period('M')
                        hist_labels.append(f"{str(period.year)[2:]}년_{period.month:02d}월")
                        hist_values.append(month['value'])
                    
                    # Current month (August)
                    current_month_label = f"{str(current_year)[2:]}년_{current_month:02d}월"
                    
                    # Future predictions (including August prediction + Sep, Oct, Nov)
                    pred_labels = []
                    pred_values = []
                    for _, row in monthly_pred.iterrows():
                        period = pd.Timestamp(row['날짜']).to_period('M')
                        pred_labels.append(f"{str(period.year)[2:]}년_{period.month:02d}월")
                        pred_values.append(row['출고량'])
                        
                    # Create Plotly figure
                    fig = go.Figure()
                    
                    # 1. Add historical line (blue solid) - up to but not including current month
                    if hist_labels:
                        fig.add_trace(go.Scatter(
                            x=hist_labels,
                            y=hist_values,
                            mode='lines+markers',
                            name='과거 실적',
                            line=dict(color='blue', width=2),
                            marker=dict(size=8, color='blue', symbol='circle-open')
                        ))
                        
                        # Connect last historical to current month actual
                        if current_month_actual > 0:
                            fig.add_trace(go.Scatter(
                                x=[hist_labels[-1], current_month_label],
                                y=[hist_values[-1], current_month_actual],
                                mode='lines',
                                line=dict(color='blue', width=2),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                    
                    # 2. Add current month actual (blue dot)
                    if current_month_actual > 0:
                        fig.add_trace(go.Scatter(
                            x=[current_month_label],
                            y=[current_month_actual],
                            mode='markers',
                            name='현재월 실적',
                            marker=dict(color='blue', size=12, symbol='circle'),
                            # text=[f'실적: {current_month_actual:.0f}'],
                            textposition='top center'
                        ))
                    
                    # 3. Add current month prediction (red diamond) - ALWAYS show if we have predictions
                    august_pred_value = None
                    
                    # First check if it's already in pred_labels
                    if current_month_label in pred_labels:
                        august_idx = pred_labels.index(current_month_label)
                        august_pred_value = pred_values[august_idx]
                    # Otherwise get it directly from the predictions structure
                    elif 'august_full_prediction' in predictions:
                        august_pred_value = predictions.get('august_full_prediction', 0)
                    elif len(forecast_values) >= 4:
                        # If we have 4 values, first one should be August
                        august_pred_value = forecast_values[0]
                    
                    # Always show the prediction dot if we have any forecast values
                    if august_pred_value is not None or len(forecast_values) > 0:
                        # Use first forecast value if august_pred_value is still None
                        if august_pred_value is None and len(forecast_values) > 0:
                            august_pred_value = forecast_values[0]
                        fig.add_trace(go.Scatter(
                            x=[current_month_label],
                            y=[august_pred_value],
                            mode='markers',
                            name='현재월 예측',
                            marker=dict(color='red', size=12, symbol='diamond'),
                            # text=[f'예측: {august_pred_value:.0f}'],
                            textposition='bottom center'
                        ))
                    
                    # 4. Add prediction line (red dotted) - all predictions including August
                    if pred_labels:
                        fig.add_trace(go.Scatter(
                            x=pred_labels,
                            y=pred_values,
                            mode='lines+markers',
                            name='예측',
                            line=dict(color='red', width=2, dash='dot'),
                            marker=dict(size=8, symbol='diamond-open', color='red')
                        ))
                        
                        # Connect last historical to first prediction if no current month actual
                        if hist_labels and current_month_actual == 0:
                            fig.add_trace(go.Scatter(
                                x=[hist_labels[-1], pred_labels[0]],
                                y=[hist_values[-1], pred_values[0]],
                                mode='lines',
                                line=dict(color='gray', width=1, dash='dot'),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                        
                    # Update layout with confidence indicator in title
                    chart_title = '월별 출고량 추이 및 예측'
                    if confidence_level == 'very_low' or method == 'baseline_insufficient_data':
                        chart_title += ' ⚠️ (데이터 부족)'
                    else:
                        chart_title += ' (현재월 실적 vs 예측 비교)'
                    
                    fig.update_layout(
                        title=chart_title,
                        xaxis_title='월',
                        yaxis_title='출고량',
                        hovermode='x unified',
                        height=400,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        )
                    )
                    
                    # Show Plotly chart
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show data table
                    with st.expander("월별 상세 데이터"):
                        # Create combined data for table
                        table_data = []
                        
                        # Add historical data
                        for i, label in enumerate(hist_labels):
                            table_data.append({
                                '월': label,
                                '출고량': int(hist_values[i]),
                                '구분': '실적'
                            })
                        
                        # Add current month
                        if current_month_actual > 0:
                            table_data.append({
                                '월': current_month_label,
                                '출고량': int(current_month_actual),
                                '구분': '현재월 실적'
                            })
                        
                        # Add predictions
                        for i, label in enumerate(pred_labels):
                            if label == current_month_label:
                                table_data.append({
                                    '월': label,
                                    '출고량': int(pred_values[i]),
                                    '구분': '현재월 예측'
                                })
                            else:
                                table_data.append({
                                    '월': label,
                                    '출고량': int(pred_values[i]),
                                    '구분': '예측'
                                })
                        
                        if table_data:
                            display_df = pd.DataFrame(table_data)
                            st.dataframe(
                                display_df,
                                use_container_width=True,
                                hide_index=True
                            )
                    
                else:
                    st.warning(f"{product}의 예측 데이터가 없습니다.")
            else:
                st.warning(f"{product}의 예측 모델이 학습되지 않았습니다.")
        else:
            if not models_loaded:
                # Show sample data
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("예측 출고량 (샘플)", "3,500개", "+12%")
                with col2:
                    st.metric("권장 발주량 (샘플)", "4,000개", help="MOQ 및 안전재고 고려")
                with col3:
                    st.metric("예측 정확도 (샘플)", "89%", help="RMSE 기반")
            else:
                st.warning(f"{product}의 예측 데이터를 찾을 수 없습니다.")
        
        # Safety stock calculation
        st.subheader("안전재고 계산")
        col1, col2 = st.columns(2)
        with col1:
            if models_loaded and selected_sku and selected_sku in future_predictions:
                # Check if using new model structure
                predictions_data = future_predictions[selected_sku]
                if 'forecast_months' in predictions_data:
                    # Check for adaptive or improved model structure
                    if 'predictions' in predictions_data:
                        # Adaptive model structure
                        forecast_values = predictions_data.get('predictions', [])
                    else:
                        # Improved model structure
                        forecast_values = predictions_data.get('arima', [])
                    
                    if len(forecast_values) > 0:
                        monthly_forecast = int(forecast_values[0])  # First month prediction
                    else:
                        monthly_forecast = 0
                else:
                    # Old model structure
                    predictions_30 = future_predictions[selected_sku].get(30, {})
                    forecast_30 = predictions_30.get('arima', [])
                    if len(forecast_30) > 0:
                        monthly_forecast = int(np.sum(forecast_30))
                    else:
                        monthly_forecast = 0
                
                if monthly_forecast > 0:
                    
                    # Get lead time from database
                    lead_time = 30  # default
                    try:
                        products_data = ProductQueries.get_all_products()
                        for p in products_data:
                            if p['상품명'] == product:
                                lead_time = p['리드타임']
                                break
                    except:
                        pass
                    
                    recommended_safety = int(monthly_forecast * (lead_time / 30))
                    
                    st.info(f"""
                    **계산 방식**
                    - 30일 예측 출고량: {monthly_forecast:,}개
                    - 리드타임: {lead_time}일
                    - 권장 안전재고 = {monthly_forecast:,} × ({lead_time}/30) = {recommended_safety:,}개
                    """)
                else:
                    st.info("예측 데이터가 없습니다.")
            else:
                st.info(f"""
                **계산 방식**
                - 30일 예측 출고량: 3,500개
                - 리드타임: 30일
                - 안전재고 = 3,500 × (30/30) = 3,500개
                """)
        with col2:
            if models_loaded and selected_sku and selected_sku in future_predictions:
                # Check if using new model structure (same logic as col1)
                predictions_data = future_predictions[selected_sku]
                if 'forecast_months' in predictions_data:
                    # Check for adaptive or improved model structure
                    if 'predictions' in predictions_data:
                        # Adaptive model structure
                        forecast_values = predictions_data.get('predictions', [])
                    else:
                        # Improved model structure
                        forecast_values = predictions_data.get('arima', [])
                    
                    if len(forecast_values) > 0:
                        monthly_forecast = int(forecast_values[0])
                    else:
                        monthly_forecast = 0
                else:
                    predictions_30 = future_predictions[selected_sku].get(30, {})
                    forecast_30 = predictions_30.get('arima', [])
                    if len(forecast_30) > 0:
                        monthly_forecast = int(np.sum(forecast_30))
                    else:
                        monthly_forecast = 0
                
                if monthly_forecast > 0:
                    st.metric("권장 안전재고", f"{recommended_safety:,}개")
                    
                    # Get current safety stock
                    current_safety = safety_stock
                    diff = recommended_safety - current_safety
                    st.metric("현재 설정값", f"{current_safety:,}개", 
                             f"{diff:+,}개" if diff != 0 else None)
                else:
                    st.metric("권장 안전재고", "N/A")
                    st.metric("현재 설정값", "N/A")
            else:
                st.metric("권장 안전재고", "3,500개")
                st.metric("현재 설정값", "3,000개", "-500개")
    
    with tabs[1]:
        st.subheader("예측값 수동 조정")
        st.warning("수동으로 조정한 값은 이력이 기록됩니다.")
        
        # Product selection OUTSIDE the form for dynamic updates
        product = st.selectbox(
            "제품 선택",
            [
                "바이오밸런스", "풍성밸런스", "클린밸런스", "뉴로마스터", "키네코어", 
                "다래 케어", "선화이버", "영데이즈", "당당케어", "칸디다웨이", "퓨어마그 펫"
            ]
        )
        
        # Get SKU and calculate predictions for selected product
        selected_sku = sku_mapping.get(product, None)
        
        # Initialize prediction values for current and 1, 2, 3 months
        pred_current = 0
        pred_2month = 0
        pred_3month = 0
        pred_4month = 0
        
        # Check for existing manual adjustments
        existing_adjustment = None
        if selected_sku:
            try:
                existing_adjustment = PredictionQueries.get_latest_adjustment(selected_sku)
            except Exception as e:
                st.error(f"기존 조정값 로드 오류: {str(e)}")
        
        # Load predictions if models are available
        if models_loaded and selected_sku and selected_sku in future_predictions:
            # Check if using improved model structure
            predictions_data = future_predictions[selected_sku]
            
            if 'forecast_months' in predictions_data:
                # Check for adaptive or improved model structure
                if 'predictions' in predictions_data:
                    # Adaptive model structure
                    forecast_values = predictions_data.get('predictions', [])
                else:
                    # Improved model structure
                    forecast_values = predictions_data.get('arima', [])
                                
                if len(forecast_values) >= 3:
                    # Direct monthly predictions
                    pred_current = int(forecast_values[0])
                    pred_2month = int(forecast_values[1])
                    pred_3month = int(forecast_values[2])
                    pred_4month = int(forecast_values[3]) if len(forecast_values) >= 4 else 0
            else:
                # Old model structure - Get 90-day predictions
                predictions_90 = future_predictions[selected_sku].get(90, {})
                forecast_values = predictions_90.get('arima', [])
                
                if len(forecast_values) > 0:
                    # Convert weekly predictions to monthly
                    # Create date range for predictions
                    last_date = predictions_90.get('last_date', datetime.now())
                    if isinstance(last_date, str):
                        last_date = pd.to_datetime(last_date)
                    
                    prediction_dates = pd.date_range(
                        start=last_date + pd.Timedelta(days=7),
                        periods=len(forecast_values),
                        freq='W'
                    )
                    
                    # Create dataframe with predictions
                    weekly_pred_df = pd.DataFrame({
                        '날짜': prediction_dates,
                        '출고량': forecast_values
                    })
                
                # Convert to monthly
                weekly_pred_df['월'] = weekly_pred_df['날짜'].dt.to_period('M')
                monthly_pred = weekly_pred_df.groupby('월')['출고량'].sum().reset_index()
                
                # Get predictions for each month
                if len(monthly_pred) >= 1:
                    pred_current = int(monthly_pred.iloc[0]['출고량'])
                if len(monthly_pred) >= 2:
                    pred_2month = int(monthly_pred.iloc[1]['출고량'])
                if len(monthly_pred) >= 3:
                    pred_3month = int(monthly_pred.iloc[2]['출고량'])
                if len(monthly_pred) >= 4:
                    pred_4month = int(monthly_pred.iloc[3]['출고량'])
        
        # Show info if existing adjustment exists
        if existing_adjustment:
            st.info(f"마지막 조정: {existing_adjustment['edited_by']} ({existing_adjustment['edited_at'].strftime('%Y-%m-%d %H:%M')})")
            if existing_adjustment['reason']:
                st.caption(f"사유: {existing_adjustment['reason']}")
        
        # Manual adjustment form
        with st.form("manual_adjustment"):
            st.markdown("### AI 예측값 및 조정")
            
            # Show predictions for each month in columns
            col2, col3, col4 = st.columns(3)  # col1, col2, col3, col4 = st.columns(4)
            
            # with col1:
            #     st.markdown("**현재 (8월)**")  # st.markdown(f"**1개월 후 ({prediction_months[0]})**")
            #     st.info(f"AI 예측: {pred_current:,}개")
            #     # Use existing adjustment if available, otherwise use AI prediction
            #     default_current = int(existing_adjustment['adjusted_current']) if existing_adjustment else pred_current
            #     adjusted_current = st.number_input(
            #         "조정값 (8월)",  # f"조정값 ({prediction_months[0]})",
            #         min_value=0,
            #         value=default_current if default_current > 0 else 100,
            #         key="adj_1month"
            #     )
            
            with col2:
                st.markdown("**1개월 후 (9월)**")  # st.markdown(f"**2개월 후 ({prediction_months[1]})**")
                st.info(f"AI 예측: {pred_2month:,}개")
                default_2month = int(existing_adjustment['adjusted_2month']) if existing_adjustment else pred_2month
                adjusted_2month = st.number_input(
                    "조정값 (9월)",  # f"조정값 ({prediction_months[1]})",
                    min_value=0,
                    value=default_2month if default_2month > 0 else 100,
                    key="adj_2month"
                )
            
            with col3:
                st.markdown("**2개월 후 (10월)**")  # st.markdown(f"**3개월 후 ({prediction_months[2]})**")
                st.info(f"AI 예측: {pred_3month:,}개")
                default_3month = int(existing_adjustment['adjusted_3month']) if existing_adjustment else pred_3month
                adjusted_3month = st.number_input(
                    "조정값 (10월)",  # f"조정값 ({prediction_months[2]})",
                    min_value=0,
                    value=default_3month if default_3month > 0 else 100,
                    key="adj_3month"
                )
            
            with col4:
                st.markdown("**3개월 후 (11월)**")  # st.markdown(f"**3개월 후 ({prediction_months[2]})**")
                st.info(f"AI 예측: {pred_4month:,}개")
                default_4month = int(existing_adjustment['adjusted_4month']) if existing_adjustment else pred_4month
                adjusted_4month = st.number_input(
                    "조정값 (11월)",  # f"조정값 ({prediction_months[3]})",
                    min_value=0,
                    value=default_4month if default_4month > 0 else 100,
                    key="adj_4month"
                )
            
            # Summary metrics
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                total_ai = pred_2month + pred_3month + pred_4month  # pred_current
                st.metric("AI 예측 총량 (다음 3개월)", f"{total_ai:,}개")
            with col2:
                total_adjusted = adjusted_2month + adjusted_3month + adjusted_4month  # adjusted_current + 
                st.metric("조정 총량 (다음 3개월)", f"{total_adjusted:,}개", 
                         f"{total_adjusted - total_ai:+,}개" if total_ai > 0 else None)
            
            # Adjustment reason
            adjustment_reason = st.text_area(
                "조정 사유 (다음 3개월)",
                placeholder="예: 프로모션 예정, 계절적 요인 등"
            )
            
            if st.form_submit_button("조정 저장"):
                # Save to database
                try:
                    # Only save if we have valid SKU and predictions
                    if selected_sku:
                        result = PredictionQueries.save_manual_adjustment(
                            master_sku=selected_sku,
                            # pred_current=float(pred_current),
                            pred_2month=float(pred_2month),
                            pred_3month=float(pred_3month),
                            pred_4month=float(pred_4month),
                            # adjusted_current=float(adjusted_current),
                            adjusted_2month=float(adjusted_2month),
                            adjusted_3month=float(adjusted_3month),
                            adjusted_4month=float(adjusted_4month),
                            reason=adjustment_reason,
                            edited_by='biocom'  # Current user
                        )
                        
                        if result:
                            st.success(f"{product}의 예측값이 조정되었습니다.")
                            
                            # Show month-by-month changes
                            changes = []
                            # if pred_current != adjusted_current:
                            #     changes.append(f"8월: {pred_current:,} → {adjusted_current:,}개")  # changes.append(f"{prediction_months[0]}: {pred_current:,} → {adjusted_current:,}개")
                            if pred_2month != adjusted_2month:
                                changes.append(f"9월: {pred_2month:,} → {adjusted_2month:,}개")  # changes.append(f"{prediction_months[1]}: {pred_2month:,} → {adjusted_2month:,}개")
                            if pred_3month != adjusted_3month:
                                changes.append(f"10월: {pred_3month:,} → {adjusted_3month:,}개")  # changes.append(f"{prediction_months[2]}: {pred_3month:,} → {adjusted_3month:,}개")
                            if pred_4month != adjusted_4month:
                                changes.append(f"11월: {pred_4month:,} → {adjusted_4month:,}개")  # changes.append(f"{prediction_months[2]}: {pred_3month:,} → {adjusted_3month:,}개")
                            
                            if changes:
                                st.info("변경 내역:\n" + "\n".join(changes))
                            
                            st.info(f"조정자: biocom | 시간: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                            
                            # # Refresh the page to show the new adjustment
                            # st.rerun()
                        else:
                            st.error("조정값 저장에 실패했습니다.")
                    else:
                        st.error("제품 SKU를 찾을 수 없습니다.")
                        
                except Exception as e:
                    st.error(f"데이터베이스 저장 오류: {str(e)}")

# Alerts page
def show_alerts():
    st.title("🔔 알림")
    
    tabs = st.tabs(["알림 목록", "알림 설정"])  # , "알림 이력"
    
    with tabs[0]:
        st.subheader("활성 알림")
        
        # Alert types
        alert_types = st.multiselect(
            "알림 유형 필터",
            ["재고 부족", "발주 시점", "소비기한 임박", "과잉 재고"],
            default=["발주 시점"]
        )
        
        # Load AI predictions if available
        future_predictions = {}
        try:
            with open('models_adaptive/future_predictions.pkl', 'rb') as f:
                future_predictions = pickle.load(f)
        except:
            try:
                with open('models/future_predictions.pkl', 'rb') as f:
                    future_predictions = pickle.load(f)
            except:
                try:
                    with open('models_improved/future_predictions.pkl', 'rb') as f:
                        future_predictions = pickle.load(f)
                except:
                    pass
        
        # SKU mapping for predictions
        sku_mapping = {
            '바이오밸런스': 'BIOBAL',
            '풍성밸런스': 'PSBAL',  # AMPLEBAL
            '클린밸런스': 'CLBAL',  # CLEANBAL
            '뉴로마스터': 'NEUROMASTER',
            '키네코어': 'KNCORE',  # KINECORE
            '다래 케어': 'DARAECARE',
            '선화이버': 'SF',  # SUNFIBER
            '영데이즈': 'YOUNGDAYS',
            '당당케어': 'DDCARE',
            '칸디다웨이': 'KDDWAY',
            '퓨어마그 펫': 'PMPKOR'
        }
        
        # Get real inventory alerts from database
        alerts_list = []
        
        # Define clean_numeric function for cleaning data
        def clean_numeric(value, default=0):
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return value
            # Handle string values that might contain formatting
            try:
                # Remove any non-numeric characters except decimal point and minus
                clean_str = str(value).strip()
                # Remove any pipe characters, table formatting, or extra spaces
                clean_str = clean_str.replace('│', '').replace('|', '').replace('┃', '')
                clean_str = clean_str.replace('─', '').replace('━', '').strip()
                # If still contains non-numeric chars, extract just the number
                import re
                match = re.search(r'-?\d+\.?\d*', clean_str)
                if match:
                    clean_str = match.group()
                # Try to convert to number
                if clean_str:
                    return float(clean_str) if '.' in clean_str else int(clean_str)
                else:
                    return default
            except Exception as e:
                print(f"Error cleaning numeric value '{value}': {e}")
                return default
        
        try:
            products = ProductQueries.get_all_products()
            if products:
                for product in products:
                    current_stock = clean_numeric(product.get('현재재고'), 0)
                    safety_stock = clean_numeric(product.get('안전재고'), 0)
                    product_name = product['상품명']
                    lead_time = clean_numeric(product.get('리드타임'), 30)
                    outbound = clean_numeric(product.get('출고량'), 0)
                    
                    # Initialize daily_usage with ordinary calculation as fallback
                    daily_usage = outbound / 30 if outbound > 0 else 0  # Fallback if no AI predictions
                    
                    ### AI 예측 시작
                    ai_safety_stock = None
                    ai_monthly_forecast = None
                    demand_trend = ''  # Default to empty when no data
                    expected_consumption_days = None  # 예상 소비일
                    
                    if product_name in sku_mapping and sku_mapping[product_name] in future_predictions:
                        pred_data = future_predictions[sku_mapping[product_name]]
                        if 'forecast_months' in pred_data:
                            # Check for adaptive or improved model structure
                            if 'predictions' in pred_data:
                                # Adaptive model structure
                                forecast_values = pred_data.get('predictions', [])
                            else:
                                # Improved model structure - use 'arima'
                                forecast_values = pred_data.get('arima', [])
                            if len(forecast_values) > 0:
                                # Calculate monthly average from available predictions
                                if len(forecast_values) >= 3:
                                    # Use all 3 months for better average
                                    avg_monthly_forecast = sum(forecast_values[:3]) / 3
                                else:
                                    # Use what we have
                                    avg_monthly_forecast = sum(forecast_values) / len(forecast_values)
                                
                                ai_monthly_forecast = int(avg_monthly_forecast)
                                
                                # Calculate demand forecast based on lead time with partial months
                                if lead_time <= 90 and len(forecast_values) >= 3:
                                    # Calculate precisely for partial months
                                    total_forecast = 0
                                    remaining_days = lead_time
                                    
                                    for month_idx, monthly_forecast in enumerate(forecast_values[:3]):
                                        if remaining_days <= 0:
                                            break
                                        
                                        if remaining_days >= 30:
                                            # Use full month
                                            total_forecast += monthly_forecast
                                            remaining_days -= 30
                                        else:
                                            # Use partial month
                                            total_forecast += monthly_forecast * (remaining_days / 30)
                                            remaining_days = 0
                                    
                                    ai_safety_stock = int(total_forecast)
                                elif lead_time > 90:
                                    # For lead times > 3 months, calculate first 3 months precisely, then extrapolate
                                    total_forecast = sum(forecast_values[:3])  # First 90 days
                                    remaining_days = lead_time - 90
                                    avg_daily = avg_monthly_forecast / 30
                                    total_forecast += avg_daily * remaining_days
                                    
                                    # Apply safety factor for uncertainty
                                    safety_factor = 1.2  # 20% safety buffer for long lead times
                                    ai_safety_stock = int(total_forecast * safety_factor)
                                else:
                                    # Fallback to simple calculation
                                    ai_safety_stock = int(avg_monthly_forecast * (lead_time / 30))
                                
                                # Calculate demand trend for 3 months
                                if len(forecast_values) >= 3:
                                    month1, month2, month3 = forecast_values[0], forecast_values[1], forecast_values[2]
                                    
                                    # Calculate the trend based on linear regression or simple comparison
                                    avg_change = ((month2 - month1) + (month3 - month2)) / 2
                                    change_rate = avg_change / month1 if month1 > 0 else 0
                                    
                                    # Determine trend based on change rate
                                    if change_rate > 0.02:  # More than 2% increase
                                        demand_trend = '상승'
                                    elif change_rate < -0.02:  # More than 2% decrease
                                        demand_trend = '하락'
                                    else:
                                        demand_trend = '유지'
                                
                                # Calculate expected consumption days
                                if current_stock > 0:
                                    remaining_stock = current_stock
                                    total_days = 0
                                    
                                    for month_idx, monthly_amount in enumerate(forecast_values[:3]):
                                        daily_rate = monthly_amount / 30
                                        
                                        if remaining_stock <= monthly_amount:
                                            # Stock runs out this month
                                            days_in_month = remaining_stock / daily_rate
                                            expected_consumption_days = int(total_days + days_in_month)
                                            break
                                        else:
                                            # Stock lasts beyond this month
                                            remaining_stock -= monthly_amount
                                            total_days += 30
                                    
                                    # If stock lasts beyond 3 months
                                    if expected_consumption_days is None and remaining_stock > 0:
                                        avg_daily = avg_monthly_forecast / 30
                                        additional_days = remaining_stock / avg_daily
                                        expected_consumption_days = int(total_days + additional_days)
                        else:
                            # Old model - use 30-day total
                            predictions_30 = pred_data.get(30, {})
                            forecast_30 = predictions_30.get('arima', [])
                            if len(forecast_30) > 0:
                                ai_monthly_forecast = int(np.sum(forecast_30))
                                
                                # Calculate demand forecast based on lead time
                                if lead_time <= 90:
                                    # For lead times up to 3 months, use direct calculation
                                    ai_safety_stock = int(ai_monthly_forecast * (lead_time / 30))
                                else:
                                    # For lead times > 3 months, use conservative estimate with safety factor
                                    base_forecast = ai_monthly_forecast * (lead_time / 30)
                                    safety_factor = 1.2  # 20% safety buffer for long lead times
                                    ai_safety_stock = int(base_forecast * safety_factor)
                                
                                # Calculate expected consumption days (simplified for old model)
                                if current_stock > 0 and ai_monthly_forecast > 0:
                                    daily_rate = ai_monthly_forecast / 30
                                    expected_consumption_days = int(current_stock / daily_rate)
                    
                    # Update daily_usage with AI predictions if available
                    if ai_monthly_forecast and ai_monthly_forecast > 0:
                        daily_usage = ai_monthly_forecast / 30  # Use AI prediction for daily usage
                    ### AI 예측 끝


                    # # 1. 재고부족
                    # 긴급
                    if safety_stock > 0 and current_stock < safety_stock * 0.5:
                        # Critical - less than 50% of safety stock
                        # Calculate days until stockout if daily_usage is available
                        days_msg = ""
                        if daily_usage > 0:
                            days_until_out = current_stock / daily_usage
                            days_msg = f" (예상 소진: {int(days_until_out)}일)"
                        
                        alerts_list.append({
                            '유형': '재고 부족',
                            '제품': product_name,
                            '상태': '긴급',
                            '안전재고_관리자': safety_stock,
                            '메시지': f'재고 {current_stock}개, 안전재고({safety_stock}개)의 50% 미만{days_msg}',
                            # '발생일시': datetime.now()
                        })
                    
                    # 주의
                    elif safety_stock > 0 and current_stock < safety_stock:
                        # Warning - below safety stock
                        # Calculate days until stockout if daily_usage is available
                        days_msg = ""
                        if daily_usage > 0:
                            days_until_out = current_stock / daily_usage
                            days_msg = f" (예상 소진: {int(days_until_out)}일)"
                        
                        alerts_list.append({
                            '유형': '재고 부족', 
                            '제품': product_name,
                            '상태': '주의',
                            '안전재고_관리자': safety_stock,
                            '메시지': f'재고 {current_stock}개, 안전재고({safety_stock}개) 미만{days_msg}',
                            # '발생일시': datetime.now()
                        })
                    

                    # # 2. 발주 시점
                    monthly_predictions = []
                    sku_for_prediction = None
                    
                    if product_name in sku_mapping:
                        sku_for_prediction = sku_mapping[product_name]
                        
                        if sku_for_prediction in future_predictions:
                            pred_data = future_predictions[sku_for_prediction]
                            
                            # Check different possible structures
                            if 'predictions' in pred_data and isinstance(pred_data['predictions'], (list, np.ndarray)):
                                # New adaptive model structure - predictions array has [Aug, Sep, Oct, Nov]
                                preds = pred_data['predictions']
                                if len(preds) >= 4:
                                    # 이번 달은(index 0) 제외하고, 다음 3달만
                                    monthly_predictions = list(preds[1:4])
                                elif len(preds) >= 3:
                                    monthly_predictions = list(preds[:3])
                            elif 'forecast_months' in pred_data:
                                if 'adaptive_forecast' in pred_data:
                                    monthly_predictions = list(pred_data['adaptive_forecast'][:3])
                                else:
                                    monthly_predictions = list(pred_data.get('arima', [])[:3])
                    
                    moq = clean_numeric(product.get('최소주문수량'), 1)
                    reorder_info = calculate_reorder_point(
                        current_stock=current_stock,
                        safety_stock=safety_stock,
                        lead_time=lead_time,
                        monthly_predictions=monthly_predictions,
                        moq=moq,
                        confidence_level=1.2 if lead_time > 90 else 1.0  # Higher confidence for long lead times
                    )
                    
                    if reorder_info['urgency'] in ['긴급', '주의']:
                        alerts_list.append({
                            '유형': '발주 시점',
                            '제품': product_name,
                            '상태': reorder_info['urgency'],
                            '수요 추이': calculate_demand_trend(monthly_predictions),
                            '안전재고량_관리자': safety_stock,
                            '현재 재고량': current_stock,
                            '리드타임': lead_time,
                            '안전재고량_예측기반': int(reorder_info['reorder_point']),
                            '일일소비량': f"{reorder_info['avg_daily_consumption']:.2f}",
                            '권장발주량': int(reorder_info['recommended_qty']),
                            '재고소진일': int(reorder_info['days_until_stockout']) if reorder_info['days_until_stockout'] != float('inf') else 'N/A',
                            # '재발주기간': int(reorder_info['days_until_reorder']) if reorder_info['days_until_reorder'] != float('inf') else 'N/A', 
                            '메시지': reorder_info['order_status'],
                        })
                    
                    # # 3. 소비기한 임박
                    if product.get('소비기한'):
                        try:
                            # Convert expiry date to datetime if it's a string
                            expiry_date = product['소비기한']
                            if isinstance(expiry_date, str):
                                expiry_date = pd.to_datetime(expiry_date).date()
                            elif hasattr(expiry_date, 'date'):
                                expiry_date = expiry_date.date()
                            
                            # Calculate days until expiry
                            today = datetime.now().date()
                            days_until_expiry = (expiry_date - today).days
                            
                            # Check if expiry alert is needed (based on slider value from settings)
                            expiry_alert_threshold = st.session_state.get('alert_settings', {}).get('expiry_alert_days', 30)
                            
                            if days_until_expiry <= expiry_alert_threshold and days_until_expiry >= 0:
                                # Determine status based on days remaining
                                if days_until_expiry <= 7:
                                    status = '긴급'
                                    # priority_msg = '즉시 할인 판매 필요'
                                elif days_until_expiry <= 14:
                                    status = '경고'
                                    # priority_msg = '할인 판매 준비'
                                elif days_until_expiry <= 21:
                                    status = '주의'
                                    # priority_msg = '판매 계획 검토'
                                else:
                                    status = ''
                                    # priority_msg = '모니터링 중'
                                
                                alerts_list.append({
                                    '유형': '소비기한 임박',
                                    '제품': product_name,
                                    '현재 재고량': current_stock,
                                    '소비기한': expiry_date.strftime('%Y-%m-%d'),
                                    '남은 일수': days_until_expiry,
                                    '상태': status,
                                    '메시지': f'소비기한 {days_until_expiry}일 남음',  #  - {priority_msg}
                                    # '권장 조치': priority_msg
                                })
                            elif days_until_expiry < 0:
                                # Already expired
                                alerts_list.append({
                                    '유형': '소비기한 임박',
                                    '제품': product_name,
                                    '현재 재고량': current_stock,
                                    '소비기한': expiry_date.strftime('%Y-%m-%d'),
                                    '남은 일수': days_until_expiry,
                                    '상태': '긴급',
                                    '메시지': f'소비기한 {abs(days_until_expiry)}일 경과 - 즉시 처리 필요',
                                    # '권장 조치': '즉시 폐기 또는 반품 처리'
                                })
                                
                        except Exception as e:
                            # Handle date parsing errors
                            continue
                    

                    # # 4. 과잉 재고
                    if daily_usage > 0:  # Only check if product has usage
                        needed_inventory = (daily_usage * lead_time) + safety_stock  # 예측 수요량 × 리드타임 + 안전재고
                        excess = current_stock - needed_inventory  # 과잉 재고 여부
                        
                        # 원래 필요한 양의 15%가 넘는다면
                        if excess > needed_inventory * 0.15:  # 과잉여부 결정
                            alerts_list.append({
                                '유형': '과잉 재고',
                                '제품': product_name,
                                '과잉': int(excess),
                                '상태': '주의',
                                '안전재고': safety_stock,  # 안전재고_관리자
                                '현재재고': current_stock,
                                '일일소비량': daily_usage,
                                '메시지': f'필요재고량의({int(needed_inventory)}개) 15% 초과',
                                # '발생일시': datetime.now()
                            })
        
        except Exception as e:
            st.error(f"알림 데이터 로드 오류: {str(e)}")
            alerts_list = []
        
        # Convert to DataFrame
        if alerts_list:
            # Filter by selected alert types
            filtered_alerts = [a for a in alerts_list if a['유형'] in alert_types]
            if filtered_alerts:
                alerts_data = pd.DataFrame(filtered_alerts)
                # Reorder columns for better display
                columns_order = ['유형', '제품', '상태']
                if '발주 시점' in alert_types and any(a['유형'] == '발주 시점' for a in filtered_alerts):
                    columns_order += ['수요 추이', '현재 재고량', '안전재고량_관리자', '리드타임', '일일소비량', '안전재고량_예측기반', '권장발주량', '재고소진일', '재발주기간', '메시지']
                elif '소비기한 임박' in alert_types and any(a['유형'] == '소비기한 임박' for a in filtered_alerts):
                    columns_order += ['현재 재고량', '소비기한', '남은 일수', '권장 조치', '메시지']
                elif '과잉 재고' in alert_types and any(a['유형'] == '과잉 재고' for a in filtered_alerts):
                    columns_order += ['과잉', '안전재고', '현재재고', '일일소비량', '메시지']
                else:
                    columns_order += ['메시지']
                columns_order += ['발생일시']
                # Only include columns that exist
                columns_order = [col for col in columns_order if col in alerts_data.columns]
                alerts_data = alerts_data[columns_order]
            else:
                alerts_data = pd.DataFrame(columns=['유형', '제품', '상태', '메시지', '발생일시'])
        else:
            alerts_data = pd.DataFrame({
                '유형': ['정보'],
                '제품': ['-'],
                '상태': ['정상'],
                '메시지': ['현재 활성 알림이 없습니다.'],
                '발생일시': [datetime.now()]
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
        
        # Color code by demand trend
        def color_trend(val):
            if val == '상승':
                return 'color: #1971c2; font-weight: bold'  # 파란색
            elif val == '하락':
                return 'color: #e03131; font-weight: bold'  # 빨간색
            elif val == '유지':
                return 'color: #2f9e44; font-weight: bold'  # 초록색
            return ''
        
        styled_df = alerts_data.style.applymap(
            color_status, 
            subset=['상태']
        )
        
        # Apply trend coloring if the column exists
        if '수요 추이' in alerts_data.columns:
            styled_df = styled_df.applymap(
                color_trend,
                subset=['수요 추이']
            )
        
        st.dataframe(
            styled_df, 
            column_config={
                '유형': st.column_config.TextColumn(
                    help="알림의 종류 (재고 부족, 발주 시점, 소비기한 임박, 과잉 재고)"
                ),
                '제품': st.column_config.TextColumn(
                    help="제품명"
                ),
                '상태': st.column_config.TextColumn(
                    help="알림의 긴급도 (긴급, 경고, 주의)",
                    width="small"
                ),
                '수요 추이': st.column_config.TextColumn(
                    help="향후 3개월간 예측 수요의 변화 추세",
                    width="small"
                ),
                '안전재고량_관리자': st.column_config.NumberColumn(
                    help="관리자가 설정한 안전재고 수량",
                    width="small"
                ),
                '현재 재고량': st.column_config.NumberColumn(
                    help="현재 보유중인 재고 수량",
                    width="small"
                ),
                '리드타임': st.column_config.NumberColumn(
                    help="발주부터 입고까지 소요되는 일수",
                    width="small",
                    format="%d일"
                ),
                '안전재고량_예측기반': st.column_config.NumberColumn(
                    help="발주가 필요한 재고 수준 (안전재고 + 리드타임 소비량)",
                    width="small",
                    format="%d개"
                ),
                '일일소비량': st.column_config.NumberColumn(
                    help="AI 예측 기반 평균 일일 소비량",
                    width="small",
                    format="%.1f개"
                ),
                '권장발주량': st.column_config.NumberColumn(
                    help="MOQ를 고려한 권장 발주 수량",
                    width="small",
                    format="%d개"
                ),
                '재고소진일': st.column_config.TextColumn(
                    help="현재 소비 속도로 재고가 소진되는 예상 일수",
                    width="small"
                ),
                '재발주기간': st.column_config.TextColumn(
                    help="며칠안에 발주해야하는지",
                    width="small"
                ),
                '수요예측': st.column_config.NumberColumn(
                    help="3개월간의 예측 출고량 평균 * (리드타임 / 30)",
                    width="small"
                ),
                '예상 소비일': st.column_config.NumberColumn(
                    help="현재 재고가 모두 소진될 것으로 예상되는 일수",
                    width="small",
                    format="%d일"
                ),
                '메시지_관리자': st.column_config.TextColumn(
                    "메시지(관리자)",
                    help="관리자 설정 기준으로 생성된 알림 메시지"
                ),
                '메시지_수요예측': st.column_config.TextColumn(
                    "메시지(AI)",
                    help="AI 예측 기준으로 생성된 알림 메시지"
                ),
                '소비기한': st.column_config.DateColumn(
                    help="제품의 소비기한",
                    width="small"
                ),
                '남은 일수': st.column_config.NumberColumn(
                    help="소비기한까지 남은 일수",
                    width="small",
                    format="%d일"
                ),
                '권장 조치': st.column_config.TextColumn(
                    help="소비기한 임박에 따른 권장 조치사항",
                    width="medium"
                ),
                '발생일시': st.column_config.DatetimeColumn(
                    help="알림이 발생한 시각",
                    format="MM/DD HH:mm"
                ),
            },
            use_container_width=True, 
            hide_index=True
        )
        
        # Quick actions
        if st.button("📋 발주표 생성"):
            st.success("발주표가 생성되었습니다.")
            
            # Generate real order sheet from products needing reorder using AI predictions
            order_list = []
            try:
                products = ProductQueries.get_all_products()
                if products:
                    products_df = pd.DataFrame(products)
                    
                    # Calculate reorder points for all products using AI predictions
                    reorder_results = batch_calculate_reorder_points(
                        products_df, 
                        future_predictions,
                        confidence_level=1.0
                    )
                    
                    # Filter products that need ordering (긴급 or 주의 status)
                    needs_order = reorder_results[reorder_results['urgency'].isin(['긴급', '주의'])]
                    needs_order = needs_order.sort_values('priority', ascending=False)
                    
                    for _, row in needs_order.iterrows():
                        # Get manufacturer from original products data
                        manufacturer = ''
                        for product in products:
                            if product['마스터_sku'] == row['마스터_sku']:
                                manufacturer = product['제조사']
                                break
                        
                        order_list.append({
                            '우선순위': row['priority'],
                            '상태': row['urgency'],
                            '제품': row['상품명'],
                            '현재 재고': int(row['현재재고']),
                            '안전재고량_예측기반': int(row['reorder_point']),
                            '권장 발주량': int(row['recommended_qty']),
                            'MOQ': int(row['MOQ']),
                            '공급업체': manufacturer,
                            '예상 입고일': (datetime.now() + pd.Timedelta(days=row['리드타임'])).strftime('%Y-%m-%d'),
                            '수요 추이': row['demand_trend']
                        })
            except Exception as e:
                st.error(f"발주표 생성 오류: {str(e)}")
            
            if order_list:
                order_sheet = pd.DataFrame(order_list)
                st.dataframe(order_sheet, use_container_width=True, hide_index=True)
                
                # Add download button for order sheet
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    order_sheet.to_excel(writer, index=False, sheet_name='발주표')
                
                st.download_button(
                    label="📥 발주표 다운로드",
                    data=buffer.getvalue(),
                    file_name=f"발주표_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.info("현재 발주가 필요한 제품이 없습니다.")
    
    with tabs[1]:
        st.subheader("알림 설정")

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

        st.markdown("**소비기한 알림**")
        expiry_alert_days = st.slider(
            "소비기한 임박 기준 (일)",
            7, 90, 30,
            help="소비기한이 N일 남으면 알림"
        )
        
        # Notification channels
        st.markdown("**알림 채널**")
        email = None
        
        # Get user email from database
        try:
            current_user = MemberQueries.get_member_by_id(st.session_state.user_id)
            user_email = current_user['email'] if current_user else ''
        except:
            user_email = ''
        email = st.text_input("이메일 주소", value=user_email or "example@email.com")
        
        # Notification send button and automatic scheduling
        st.markdown("**자동 알림 스케줄링**")
        
        # Initialize scheduler in session state if not exists
        if 'notification_scheduler' not in st.session_state:
            st.session_state.notification_scheduler = None
        
        # Automatic notification time
        notification_time = st.time_input(
            "매일 알림 시간",
            value=pd.to_datetime("09:00").time(),
            help="매일 지정된 시간에 자동으로 알림을 발송합니다"
        )
        
        # Toggle for automatic notifications
        auto_notify = st.checkbox("자동 알림 활성화", value=False)
        
        if auto_notify and email:
            if st.button("🔄 자동 알림 시작", use_container_width=True):
                try:
                    # Stop existing scheduler if running
                    if st.session_state.notification_scheduler:
                        st.session_state.notification_scheduler.stop()
                    
                    # Create new scheduler with current settings
                    scheduler = NotificationScheduler()
                    scheduler.notification_email = email
                    scheduler.notification_time = notification_time.strftime("%H:%M")
                    scheduler.stock_alert_days = stock_alert_days
                    scheduler.order_alert_days = order_alert_days
                    scheduler.expiry_alert_days = expiry_alert_days
                    
                    # Start scheduler
                    scheduler.start()
                    st.session_state.notification_scheduler = scheduler
                    
                    st.success(f"자동 알림이 활성화되었습니다. 매일 {notification_time.strftime('%H:%M')}에 알림이 발송됩니다.")
                    
                    # Save scheduler info to environment or database
                    os.environ['NOTIFICATION_EMAIL'] = email
                    os.environ['NOTIFICATION_TIME'] = notification_time.strftime("%H:%M")
                    os.environ['STOCK_ALERT_DAYS'] = str(stock_alert_days)
                    os.environ['ORDER_ALERT_DAYS'] = str(order_alert_days)
                    os.environ['EXPIRY_ALERT_DAYS'] = str(expiry_alert_days)
                    
                except Exception as e:
                    import traceback
                    st.error(f"자동 알림 설정 오류: {str(e)}")
                    st.text(f"Error details: {traceback.format_exc()}")
        
        elif st.session_state.notification_scheduler:
            if st.button("⏹ 자동 알림 중지", use_container_width=True):
                try:
                    st.session_state.notification_scheduler.stop()
                    st.session_state.notification_scheduler = None
                    st.success("자동 알림이 중지되었습니다.")
                except Exception as e:
                    st.error(f"자동 알림 중지 오류: {str(e)}")
        
        # Check if user is admin
        is_admin = False
        try:
            current_user = MemberQueries.get_member_by_id(st.session_state.user_id)
            is_admin = current_user.get('master', False) if current_user else False
        except:
            is_admin = False
        
        if email and is_admin:
            if st.button("📧 즉시 알림 발송", use_container_width=True):
                # Collect current alerts
                alerts_for_email = []
                
                # Load AI predictions for forecast-based calculations
                future_predictions = {}
                try:
                    with open('models_adaptive/future_predictions.pkl', 'rb') as f:
                        future_predictions = pickle.load(f)
                except:
                    pass
                
                # SKU mapping for predictions
                sku_mapping = {
                    '바이오밸런스': 'BIOBAL',
                    '풍성밸런스': 'PSBAL',  # AMPLEBAL
                    '클린밸런스': 'CLBAL',  # CLEANBAL
                    '뉴로마스터': 'NEUROMASTER',
                    '키네코어': 'KNCORE',  # KINECORE
                    '다래 케어': 'DARAECARE',
                    '선화이버': 'SF',  # SUNFIBER
                    '영데이즈': 'YOUNGDAYS',
                    '당당케어': 'DDCARE',
                    '칸디다웨이': 'KDDWAY',
                    '퓨어마그 펫': 'PMPKOR'
                }
                
                try:
                    products = ProductQueries.get_all_products()
                    if products:
                        for product in products:
                            # Clean numeric values to handle any formatting issues
                            def clean_numeric(value, default=0):
                                if value is None:
                                    return default
                                if isinstance(value, (int, float)):
                                    return value
                                # Handle string values that might contain formatting
                                try:
                                    # Remove any non-numeric characters except decimal point and minus
                                    clean_str = str(value).strip()
                                    # Remove any pipe characters, table formatting, or extra spaces
                                    clean_str = clean_str.replace('│', '').replace('|', '').replace('┃', '')
                                    clean_str = clean_str.replace('─', '').replace('━', '').strip()
                                    # If still contains non-numeric chars, extract just the number
                                    import re
                                    match = re.search(r'-?\d+\.?\d*', clean_str)
                                    if match:
                                        clean_str = match.group()
                                    # Try to convert to number
                                    if clean_str:
                                        return float(clean_str) if '.' in clean_str else int(clean_str)
                                    else:
                                        return default
                                except Exception as e:
                                    print(f"Error cleaning numeric value '{value}': {e}")
                                    return default
                            
                            current_stock = clean_numeric(product.get('현재재고'), 0)
                            safety_stock = clean_numeric(product.get('안전재고'), 0)
                            product_name = product['상품명']
                            lead_time = clean_numeric(product.get('리드타임'), 30)
                            outbound = clean_numeric(product.get('출고량'), 0)
                            expiration = product.get('소비기한')
                            
                            daily_usage = outbound / 30 if outbound > 0 else 0
                            
                            # Calculate expected_consumption_days using forecast (same as main logic)
                            expected_consumption_days = 0
                            forecast_values = []
                            
                            # Check if we have AI predictions for this product
                            if product_name in sku_mapping and sku_mapping[product_name] in future_predictions:
                                pred_data = future_predictions[sku_mapping[product_name]]
                                if 'forecast_months' in pred_data:
                                    # New model - use forecast
                                    forecast_values = list(pred_data.get('arima', []))
                                elif 'predictions' in pred_data:
                                    # Old model structure
                                    preds = pred_data['predictions']
                                    if 'arima' in preds and len(preds['arima']) >= 3:
                                        forecast_values = list(preds['arima'][:3])
                            
                            # Calculate expected consumption days using forecast if available
                            if len(forecast_values) > 0 and current_stock > 0:
                                remaining_stock = current_stock
                                total_days = 0
                                
                                for month_idx, monthly_amount in enumerate(forecast_values[:3]):
                                    daily_rate = monthly_amount / 30 if monthly_amount > 0 else 0.1
                                    
                                    if daily_rate > 0 and remaining_stock <= monthly_amount:
                                        # Stock runs out this month
                                        days_in_month = remaining_stock / daily_rate
                                        expected_consumption_days = int(total_days + days_in_month)
                                        break
                                    else:
                                        # Stock lasts beyond this month
                                        remaining_stock -= monthly_amount
                                        total_days += 30
                                
                                # If stock lasts beyond 3 months
                                if expected_consumption_days == 0 and remaining_stock > 0:
                                    avg_monthly = sum(forecast_values[:3]) / len(forecast_values[:3])
                                    avg_daily = avg_monthly / 30 if avg_monthly > 0 else 0.1
                                    additional_days = remaining_stock / avg_daily
                                    expected_consumption_days = int(total_days + additional_days)
                            else:
                                # No forecast available, use simple calculation
                                if daily_usage > 0 and current_stock > 0:
                                    expected_consumption_days = int(current_stock / daily_usage)
                            
                            # Check if stock alert is needed
                            if daily_usage > 0:
                                try:
                                    days_until_stockout = float(current_stock) / float(daily_usage)
                                except (ValueError, TypeError):
                                    days_until_stockout = 0
                                
                                # Stock depletion alert - only if below safety stock
                                if current_stock < safety_stock and days_until_stockout > 0:
                                    stockout_date = (datetime.now() + pd.Timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')
                                    
                                    # Determine status based on how critical the stock level is
                                    if current_stock < safety_stock * 0.5:
                                        status = '긴급'
                                    else:
                                        status = '주의'
                                    
                                    try:
                                        days_text = int(days_until_stockout)
                                    except:
                                        days_text = round(days_until_stockout)
                                    
                                    alerts_for_email.append({
                                        '제품': product_name,
                                        '유형': '재고 부족',
                                        '현재 재고량': current_stock,
                                        '안전재고량': safety_stock,
                                        # '예상 소진일': stockout_date,
                                        '예상 소비일': expected_consumption_days,
                                        '리드타임': lead_time,
                                        '상태': status,
                                        '메시지': f'{days_text}일 후 재고 소진 예상'
                                    })
                                
                                # 발주시점 알림
                                if days_until_stockout > 0:
                                    days_until_reorder = days_until_stockout - lead_time
                                    if days_until_reorder <= order_alert_days and days_until_reorder <= lead_time:
                                        # Determine urgency based on how soon we need to order
                                        if days_until_reorder <= 0:
                                            order_status = '긴급'
                                            order_message = '즉시 발주 필요'
                                        elif days_until_reorder <= 3:
                                            order_status = '경고'
                                            try:
                                                order_message = f'{int(days_until_reorder)}일 내 발주 필요'
                                            except:
                                                order_message = f'{days_until_reorder:.0f}일 내 발주 필요'
                                        else:
                                            order_status = '주의'
                                            try:
                                                order_message = f'{int(days_until_reorder)}일 내 발주 권장'
                                            except:
                                                order_message = f'{days_until_reorder:.0f}일 내 발주 권장'
                                        
                                        alerts_for_email.append({
                                            '제품': product_name,
                                            '유형': '발주 시점',
                                            '현재 재고량': current_stock,
                                            '안전재고량': safety_stock, 
                                            '출고량': outbound,
                                            # '예상 소진일': stockout_date,
                                            '예상 소비일': expected_consumption_days,
                                            '리드타임': lead_time,
                                            '상태': order_status,
                                            '메시지': order_message
                                        })
                            
                            # 소비기한 임박
                            if expiration:
                                if isinstance(expiration, str):
                                    try:
                                        expiration = pd.to_datetime(expiration).date()
                                    except:
                                        expiration = None
                                
                                if expiration:
                                    days_until_expiry = (expiration - datetime.now().date()).days
                                    if days_until_expiry <= expiry_alert_days:
                                        status = '긴급' if days_until_expiry <= 7 else ('경고' if days_until_expiry <= 14 else '주의')
                                        
                                        alerts_for_email.append({
                                            '제품': product_name,
                                            '유형': '소비기한 임박',
                                            '현재 재고량': current_stock,
                                            '소비기한': expiration.strftime('%Y-%m-%d'),
                                            '남은 일수': days_until_expiry,
                                            '상태': status,
                                            '권장 조치': '판촉 진행 또는 폐기 준비'
                                        })
                
                    if alerts_for_email:
                        # Send test email
                        email_system = EmailAlertSystem()
                        
                        if not email_system.is_configured:
                            # Show preview instead
                            st.warning("SMTP가 설정되지 않았습니다. 이메일 미리보기를 생성합니다.")
                            preview_path = email_system.save_alert_preview(email, alerts_for_email)
                            if preview_path:
                                st.success("이메일 미리보기가 생성되었습니다.")
                                
                                # Show the HTML content in expandable section
                                with st.expander("📧 이메일 미리보기"):
                                    with open(preview_path, 'r', encoding='utf-8') as f:
                                        html_content = f.read()
                                    st.components.v1.html(html_content, height=600, scrolling=True)
                                
                                st.info("실제 이메일을 발송하려면 EMAIL_SETUP.md 파일을 참고하여 SMTP 설정을 완료해주세요.")
                        else:
                            if email_system.send_inventory_alert(email, alerts_for_email):
                                st.success(f"테스트 이메일이 {email}로 발송되었습니다.")
                            else:
                                st.error("이메일 발송에 실패했습니다. SMTP 설정을 확인해주세요.")
                    else:
                        st.info("현재 알림이 필요한 제품이 없습니다.")
                
                except Exception as e:
                    st.error(f"이메일 발송 오류: {str(e)}")
        
        st.markdown("---")
        
        if st.button("설정 저장", use_container_width=True):
            # Save alert settings to session state or database
            st.session_state.alert_settings = {
                'stock_alert_days': stock_alert_days,
                'order_alert_days': order_alert_days,
                'expiry_alert_days': expiry_alert_days,
                # 'sms_notify': sms_notify,
                # 'phone': phone if sms_notify else None
            }
            st.success("알림 설정이 저장되었습니다.")

# Member info page
def member_info():
    st.title("회원 정보")
    
    # Get current user information
    user_id = st.session_state.user_id
    current_user = MemberQueries.get_member_by_id(user_id)
    
    if not current_user:
        st.error("사용자 정보를 불러올 수 없습니다.")
        return
    
    # Display current user information
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("현재 정보")
        st.info(f"**사용자 ID:** {current_user['id']}")
        st.info(f"**이름:** {current_user['name']}")
        st.info(f"**이메일:** {current_user['email']}")
        st.info(f"**전화번호:** {current_user['phone_no'] or '미등록'}")
        st.info(f"**권한:** {'관리자' if current_user['master'] == True else '일반 사용자'}")
    
    with col2:
        st.subheader("정보 수정")
        
        # Change password form
        with st.form("change_password_form"):
            st.markdown("### 비밀번호 변경")
            old_password = st.text_input("현재 비밀번호", type="password")
            new_password = st.text_input("새 비밀번호", type="password", help="6자 이상 입력하세요")
            confirm_password = st.text_input("새 비밀번호 확인", type="password")
            
            if st.form_submit_button("비밀번호 변경", use_container_width=True):
                if not all([old_password, new_password, confirm_password]):
                    st.error("모든 필드를 입력해주세요.")
                elif len(new_password) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                elif new_password != confirm_password:
                    st.error("새 비밀번호가 일치하지 않습니다.")
                else:
                    try:
                        result = MemberQueries.update_member_password(user_id, old_password, new_password)
                        if result:
                            st.success("비밀번호가 성공적으로 변경되었습니다.")
                        else:
                            st.error("현재 비밀번호가 올바르지 않습니다.")
                    except Exception as e:
                        st.error(f"비밀번호 변경 중 오류가 발생했습니다: {str(e)}")
        
        # Update basic info form
        with st.form("update_info_form"):
            st.markdown("### 기본 정보 변경")
            new_email = st.text_input("새 이메일", value=current_user['email'])
            new_phone = st.text_input("새 전화번호", value=current_user['phone_no'] or '')
            
            if st.form_submit_button("정보 수정", use_container_width=True):
                try:
                    result = MemberQueries.update_member_info(user_id, new_email, new_phone)
                    if result:
                        st.success("정보가 성공적으로 수정되었습니다.")
                        # Update session state
                        st.session_state.user_info['email'] = new_email
                        st.session_state.user_info['phone_no'] = new_phone
                        # st.rerun()
                except Exception as e:
                    st.error(f"정보 수정 중 오류가 발생했습니다: {str(e)}")

# Member Management page
def show_member_management():
    st.title("관리자 페이지")
    
    # Check if user is master
    user_id = st.session_state.user_id
    current_user = MemberQueries.get_member_by_id(user_id)
    
    if not current_user or current_user['master'] != True:
        st.error("⚠️ 관리자 권한이 필요합니다.")
        if st.button("돌아가기"):
            st.session_state.current_page = "member"
            st.rerun()
        return
    
    tabs = st.tabs(["회원 정보 수정", "입출고 수정 요청", "API 키 관리"])  # , "신규 회원 등록"
    
    with tabs[0]:
        st.subheader("회원 정보 수정")
        st.info("아래 회원의 이메일, 전화번호 정보를 직접 수정하시고 변경사항 저장을 누르세요.")
        
        # Show success message if exists in session state
        if 'member_update_message' in st.session_state:
            st.success(st.session_state.member_update_message)
            del st.session_state.member_update_message
        
        # Load member data
        try:
            member_list = MemberQueries.get_all_members()
            
            if member_list:
                # Convert to DataFrame for easier manipulation
                original_df = pd.DataFrame(member_list)
                
                # Create display dataframe with selected columns
                display_df = original_df[['id', 'name', 'master', 'email', 'phone_no', 'joined_date', 'last_update_time']].copy()
                display_df['master'] = display_df['master'].apply(lambda x: '🔑 관리자' if x else '👤 일반회원')
                
                # Format dates (handle NULL values for joined_date)
                display_df['joined_date'] = pd.to_datetime(display_df['joined_date'], errors='coerce').dt.strftime('%Y-%m-%d')
                display_df['joined_date'] = display_df['joined_date'].fillna('미등록')  # Fill NULL with '미등록' (Not registered)
                display_df['last_update_time'] = pd.to_datetime(display_df['last_update_time']).dt.strftime('%Y-%m-%d %H:%M')
                
                # Rename columns for display
                display_df.columns = ['ID', '이름', '권한', '이메일', '전화번호', '가입일', '최근수정']
                
                # Create editable dataframe
                edited_df = st.data_editor(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    disabled=['ID', '이름', '권한', '가입일', '최근수정'],  # These columns cannot be edited
                    key="member_editor",
                    num_rows="fixed",
                    column_config={
                        "ID": st.column_config.TextColumn("ID", width="small"),
                        "이름": st.column_config.TextColumn("이름", width="small"),
                        "권한": st.column_config.TextColumn("권한", width="small"),
                        "이메일": st.column_config.TextColumn("이메일", width="medium"),
                        "전화번호": st.column_config.TextColumn("전화번호", width="medium"),
                        "가입일": st.column_config.TextColumn("가입일", width="small"),
                        "최근수정": st.column_config.TextColumn("최근수정", width="medium"),
                    }
                )
                
                # Save changes button
                if st.button("변경사항 저장", type="primary"):
                    try:
                        changes_made = False
                        errors = []
                        success_count = 0
                        
                        for idx in range(len(display_df)):
                            # Get the member ID (primary key)
                            member_id = display_df.iloc[idx]['ID']
                            
                            # Check if email or phone was modified
                            original_email = display_df.iloc[idx]['이메일']
                            original_phone = display_df.iloc[idx]['전화번호']
                            edited_email = edited_df.iloc[idx]['이메일']
                            edited_phone = edited_df.iloc[idx]['전화번호']
                            
                            if original_email != edited_email or original_phone != edited_phone:
                                try:
                                    result = MemberQueries.update_member_info(
                                        member_id, 
                                        edited_email if edited_email else '',
                                        edited_phone if edited_phone else ''
                                    )
                                    if result:
                                        changes_made = True
                                        success_count += 1
                                except Exception as e:
                                    errors.append(f"회원 {member_id} 수정 실패: {str(e)}")
                        
                        # Show results
                        if changes_made:
                            st.session_state.member_update_message = f"✅ {success_count}명의 회원 정보가 성공적으로 수정되었습니다."
                            st.rerun()
                        else:
                            st.info("변경사항이 없습니다.")
                        
                        if errors:
                            for error in errors:
                                st.error(error)
                                
                    except Exception as e:
                        st.error(f"저장 중 오류 발생: {str(e)}")
            else:
                st.warning("등록된 회원이 없습니다.")
                
        except Exception as e:
            st.error(f"회원 목록을 불러오는 중 오류가 발생했습니다: {str(e)}")
    
    with tabs[1]:
        st.subheader("입출고 수정 요청")
        inout_list = ShipmentQueries.get_all_inv_adjust()

        if inout_list:
            inout_df = pd.DataFrame(inout_list)

            inout_df = inout_df[
                ['마스터_sku', '상품명', '제조사', '입출고_여부',
                '수량_old', '수량_new', '시점_old', '시점_new', 
                '요청자명', '사유', '승인']
            ]
            
            st.dataframe(inout_df)
    
    with tabs[2]:
        st.subheader("API 키 관리")
        st.markdown("외부 시스템에서 재고 API에 접근할 수 있는 보안 키를 생성하고 관리합니다.")
        
        # Create sub-tabs for API key management
        api_tabs = st.tabs(["새 API 키 생성", "기존 API 키 관리"])
        
        with api_tabs[0]:
            st.info("API 키는 외부 시스템에서 재고 조회 및 입출고 처리를 위해 사용됩니다.")
            
            with st.form("generate_api_key"):
                col1, col2 = st.columns(2)
                
                with col1:
                    key_name = st.text_input(
                        "API 키 이름", 
                        placeholder="예: 프로덕션 서버, 모바일 앱",
                        help="이 API 키를 식별할 수 있는 이름"
                    )
                    
                with col2:
                    permissions = st.multiselect(
                        "권한",
                        options=["read", "write"],
                        default=["read", "write"],
                        help="이 키가 수행할 수 있는 작업 선택"
                    )
                
                generate_btn = st.form_submit_button("🔑 API 키 생성", type="primary")
                
                if generate_btn and key_name:
                    # Generate a secure API key
                    api_key = secrets.token_urlsafe(32)
                    
                    # Hash the key for storage
                    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                    
                    # Save to database
                    try:
                        result = ApiKeyQueries.create_api_key(
                            key_hash=key_hash,
                            name=key_name,
                            created_by=st.session_state.user_id,
                            permissions=",".join(permissions)
                        )
                        
                        # Display the generated key
                        st.success("✅ API 키가 성공적으로 생성되었습니다!")
                        
                        # Important warning
                        st.warning("⚠️ **중요**: 이 API 키를 안전하게 보관하세요. 다시 표시되지 않습니다!")
                        
                        # Display the key
                        st.code(api_key, language=None)
                        
                        # Show usage instructions
                        with st.expander("API 키 사용 방법"):
                            st.markdown("""
                            ### API 키 사용하기
                            
                            요청 헤더에 `X-API-Key`를 포함하세요:
                            
                            **cURL 예제:**
                            ```bash
                            curl -H "X-API-Key: YOUR_API_KEY" \\
                                 http://localhost:8010/api/stock/SKU001
                            ```
                            
                            **Python 예제:**
                            ```python
                            import requests
                            
                            headers = {"X-API-Key": "YOUR_API_KEY"}
                            response = requests.get(
                                "http://localhost:8010/api/stock/SKU001",
                                headers=headers
                            )
                            ```
                            """)
                        
                    except Exception as e:
                        st.error(f"API 키 생성 실패: {str(e)}")
                        st.info("데이터베이스에 playauto_api_keys 테이블이 있는지 확인하세요.")
                elif generate_btn:
                    st.error("API 키 이름을 입력하세요.")
        
        with api_tabs[1]:
            st.info("생성된 API 키 목록과 사용 현황")
            
            try:
                # Get all API keys (master sees all)
                api_keys = ApiKeyQueries.get_all_api_keys()
                
                if api_keys:
                    # Convert to DataFrame for display
                    df = pd.DataFrame(api_keys)
                    
                    # Format the DataFrame
                    df['created_at'] = pd.to_datetime(df['created_at'])
                    if 'last_used' in df.columns:
                        df['last_used'] = pd.to_datetime(df['last_used'])
                    
                    # Create display dataframe
                    display_df = df[['key_id', 'name', 'permissions', 'is_active', 'created_by', 'created_at']].copy()
                    display_df['is_active'] = display_df['is_active'].apply(lambda x: '✅ 활성' if x else '❌ 비활성')
                    display_df['created_at'] = display_df['created_at'].dt.strftime('%Y-%m-%d %H:%M')
                    
                    # Add last used info if available
                    if 'last_used' in df.columns:
                        display_df['last_used'] = df['last_used'].dt.strftime('%Y-%m-%d %H:%M')
                        display_df['last_used'] = display_df['last_used'].fillna('사용 안함')
                    
                    # Rename columns for display
                    columns_rename = {
                        'key_id': 'ID',
                        'name': '키 이름',
                        'permissions': '권한',
                        'is_active': '상태',
                        'created_by': '생성자',
                        'created_at': '생성일'
                    }
                    if 'last_used' in display_df.columns:
                        columns_rename['last_used'] = '최근 사용'
                    
                    display_df.rename(columns=columns_rename, inplace=True)
                    
                    # Display the dataframe
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # Revoke key functionality
                    st.markdown("### API 키 비활성화")
                    key_to_revoke = st.selectbox(
                        "비활성화할 API 키 선택",
                        options=df[df['is_active'] == True]['key_id'].tolist() if any(df['is_active']) else [],
                        format_func=lambda x: f"{df[df['key_id']==x]['name'].values[0]} (ID: {x})"
                    )
                    
                    if st.button("🗑️ 선택한 키 비활성화", type="secondary"):
                        try:
                            ApiKeyQueries.deactivate_api_key(key_to_revoke)
                            st.success("API 키가 비활성화되었습니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"키 비활성화 실패: {str(e)}")
                else:
                    st.info("생성된 API 키가 없습니다.")
                    
            except Exception as e:
                st.error(f"API 키 목록을 불러오는 중 오류 발생: {str(e)}")
                st.info("데이터베이스에 playauto_api_keys 테이블이 있는지 확인하세요.")


if __name__ == "__main__":
    main()
