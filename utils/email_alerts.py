import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os
from typing import List, Dict
import pandas as pd
import schedule
import time
import threading
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.database import ProductQueries

class EmailAlertSystem:
    def __init__(self):
        # Email configuration - should be moved to environment variables
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.sender_email = os.getenv('SENDER_EMAIL', '')
        self.sender_password = os.getenv('SENDER_PASSWORD', '')
        
        # Check if email is properly configured
        self.is_configured = bool(self.sender_email and self.sender_password)
        
    def send_inventory_alert(self, recipient_email: str, alerts: List[Dict]) -> bool:
        """Send inventory shortage alert email"""
        if not self.is_configured:
            print("Email not configured. Please set SENDER_EMAIL and SENDER_PASSWORD in .env file")
            return False
            
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'[PLAYAUTO] 재고 부족 알림 - {datetime.now().strftime("%Y-%m-%d")}'
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            
            # Create HTML content
            html_content = self._create_inventory_alert_html(alerts)
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                
            return True
            
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return False
    
    def save_alert_preview(self, recipient_email: str, alerts: List[Dict]) -> str:
        """Save alert preview as HTML file for testing without SMTP"""
        try:
            html_content = self._create_inventory_alert_html(alerts)
            
            # Save to file
            filename = f"alert_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            filepath = os.path.join(os.path.dirname(__file__), '..', filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return filepath
        except Exception as e:
            print(f"Error saving preview: {str(e)}")
            return None
    
    def _create_inventory_alert_html(self, alerts: List[Dict]) -> str:
        """Create HTML content for inventory alerts"""
        
        # Group alerts by type first
        stock_alerts = [a for a in alerts if a.get('유형') == '재고 부족']
        order_alerts = [a for a in alerts if a.get('유형') == '발주 시점']
        expiry_alerts = [a for a in alerts if a.get('유형') == '소비기한 임박']
        
        # No need to group by urgency anymore - we'll handle them in unified tables
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background-color: #f4f4f4; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .alert-section {{ margin-bottom: 30px; }}
                .urgent {{ color: #d32f2f; }}
                .warning {{ color: #f57c00; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f4f4f4; }}
                .urgent-row {{ background-color: #ffebee; }}
                .warning-row {{ background-color: #fff3e0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>PLAYAUTO 재고 알림</h1>
                <p>{datetime.now().strftime("%Y년 %m월 %d일")} 재고 현황</p>
            </div>
            
            <div class="content">
        """
        
        # # 발주 시점 알림
        if order_alerts:
            # Sort by status priority: 긴급 first, then 주의 (no 경고 for order alerts in main logic)
            sorted_order_alerts = sorted(order_alerts, key=lambda x: 0 if x.get('상태') == '긴급' else 1)
            
            html += """
                <div class="alert-section">
                    <h2 style="color: #2196F3;">📦 발주 시점 알림</h2>
                    <table>
                        <tr>
                            <th>제품명</th>
                            <th>안전재고</th>
                            <th>현재 재고</th>
                            <th>리드타임</th>
                            <th>상태</th>
                            <th>메시지</th>
                        </tr>
            """
            
            for alert in sorted_order_alerts:
                status = alert.get('상태', '')
                safety_stock = alert.get('안전재고량', 0)
                current_stock = alert.get('현재 재고량', 0)
                lead_time = alert.get('리드타임', 0)
                
                # Get daily usage for calculations (from 출고량/30 like in app.py)
                outbound = alert.get('출고량', 0)
                daily_usage = outbound / 30 if outbound > 0 else 0
                
                expected_consumption_days = alert.get('예상 소비일', 0)
                # Only calculate if not provided
                if expected_consumption_days == 0 and daily_usage > 0 and current_stock > 0:
                    # Simple calculation based on constant daily usage
                    expected_consumption_days = int(current_stock / daily_usage)
                
                if safety_stock > 0:
                    # 주의: current_stock > safety_stock
                    if current_stock > safety_stock:
                        # Should be 주의 (if it's in the alert list)
                        if status != '주의' and status in ['긴급', '경고']:
                            status = '주의'
                    # 긴급: current_stock <= safety_stock
                    elif current_stock <= safety_stock:
                        # Should be 긴급
                        if status != '긴급':
                            status = '긴급'
                
                # Generate messages following app.py main alert logic exactly
                if status == '긴급':
                    row_class = "urgent-row"
                    status_emoji = "🚨"
                    # 긴급: current_stock <= safety_stock
                    # Calculate days until stockout (following app.py line 2049)
                    if daily_usage > 0:
                        days_until_stockout = int(current_stock / daily_usage)
                        # Message format from app.py line 2071
                        message = f'{days_until_stockout}일 후 재고 소진, 리드타임 {lead_time}일'
                    else:
                        # Fallback to original message if can't calculate
                        message = alert.get('메시지', f'즉시 발주 필요 (리드타임 {lead_time}일)')
                        
                elif status == '주의':
                    row_class = ""
                    status_emoji = "📋"
                    # Debug: Print values for 주의 status
                    print(f"\n=== 주의 Product: {alert.get('제품')} ===")
                    print(f"Current stock: {current_stock}")
                    print(f"Outbound: {outbound}")
                    print(f"Daily usage: {daily_usage}")
                    print(f"Expected consumption days from alert: {alert.get('예상 소비일', 'Not provided')}")
                    print(f"Expected consumption days calculated: {expected_consumption_days}")
                    print(f"Lead time: {lead_time}")
                    print(f"Condition met? {expected_consumption_days >= lead_time if expected_consumption_days > 0 else 'No (consumption=0)'}")
                    
                    # 주의: current_stock > safety_stock
                    # Calculate days until below safety stock (following app.py line 2015)
                    if daily_usage > 0 and current_stock > safety_stock:
                        days_until_below_safety = int((current_stock - safety_stock) / daily_usage)
                        # Message format from app.py line 2042 exactly:
                        # if expected_consumption_days < lead_time: first message
                        # else: second message
                        if expected_consumption_days > 0:
                            if expected_consumption_days < lead_time:
                                message = f'{days_until_below_safety}일 후 안전재고(관리자 기준) 도달 예정 - 발주 필요'
                            else:
                                days_remaining = int(expected_consumption_days - lead_time)
                                message = f'리드타임까지 {days_remaining}일 남았습니다.'
                                # Debug: Add info to see values
                                message += f' (소비:{expected_consumption_days}일, 리드:{lead_time}일)'
                                print('발주 시점 메시지:\n', message)
                        else:
                            # If no expected_consumption_days, use the first format
                            message = f'{days_until_below_safety}일 후 안전재고(관리자 기준) 도달 예정 - 발주 필요'
                    else:
                        # Fallback to original message if can't calculate
                        message = alert.get('메시지', '발주 권장')
                        
                elif status == '경고':
                    row_class = "warning-row" 
                    status_emoji = "⚠️"
                    # 경고 is from email alert logic, not main logic
                    # Use the message from app.py email alerts (e.g., "X일 내 발주 필요")
                    message = alert.get('메시지', '')
                    
                else:
                    row_class = ""
                    status_emoji = ""
                    message = alert.get('메시지', '')
                
                html += f"""
                        <tr class="{row_class}">
                            <td><strong>{alert.get('제품', '')}</strong></td>
                            <td>{safety_stock:,}개</td>
                            <td>{current_stock:,}개</td>
                            <td>{lead_time}일</td>
                            <td>{status_emoji} {status}</td>
                            <td>{message}</td>
                        </tr>
                """
            
            html += """
                    </table>
                </div>
            """
        
        # # 재고 부족 현황
        if stock_alerts:
            # Filter out alerts with '경고' status and sort by priority: 긴급 first, then 주의
            filtered_stock_alerts = [a for a in stock_alerts if a.get('상태') != '경고']
            sorted_stock_alerts = sorted(filtered_stock_alerts, key=lambda x: 0 if x.get('상태') == '긴급' else 1)
            
            html += """
                <div class="alert-section">
                    <h2 style="color: #ff6b6b;">📦 재고 부족 현황</h2>
                    <table>
                        <tr>
                            <th>제품명</th>
                            <th>현재 재고</th>
                            <th>안전재고</th>
                            <th>상태</th>
                            <th>메시지</th>
                        </tr>
            """
            
            for alert in sorted_stock_alerts:
                status = alert.get('상태', '')
                current_stock = alert.get('현재 재고량', 0)
                safety_stock = alert.get('안전재고량', alert.get('안전재고_관리자', 0))
                
                # Generate message following app.py logic exactly
                if status == '긴급':
                    row_class = "urgent-row"
                    status_emoji = "🚨"
                    # Same format as app.py: 재고 X개, 안전재고(Y개)의 50% 미만
                    message = f'현재 재고 {current_stock:,}개, 안전재고({safety_stock:,}개)의 50% 미만'
                elif status == '주의':
                    row_class = ""
                    status_emoji = "📋"
                    # Same format as app.py: 재고 X개, 안전재고(Y개) 미만
                    message = f'현재 재고 {current_stock:,}개, 안전재고({safety_stock:,}개) 미만'
                else:
                    row_class = ""
                    status_emoji = ""
                    message = alert.get('메시지', '')
                
                html += f"""
                        <tr class="{row_class}">
                            <td><strong>{alert.get('제품', '')}</strong></td>
                            <td>{current_stock:,}개</td>
                            <td>{safety_stock:,}개</td>
                            <td>{status_emoji} {status}</td>
                            <td>{message}</td>
                        </tr>
                """
            
            html += """
                    </table>
                </div>
            """
        
        # Add expiry alerts section
        if expiry_alerts:
            # Separate expired and non-expired products
            expired_products = [a for a in expiry_alerts if a.get('남은 일수', 0) < 0]
            non_expired_products = [a for a in expiry_alerts if a.get('남은 일수', 0) >= 0]
            
            # Sort non-expired by days remaining (urgent first)
            non_expired_products.sort(key=lambda x: x.get('남은 일수', 999))
            
            html += """
                <div class="alert-section">
                    <h2 style="color: #FF6B6B;">⏰ 소비기한 임박</h2>
                    <table>
                        <tr>
                            <th>제품명</th>
                            <th>현재 재고</th>
                            <th>소비기한</th>
                            <th>남은 일수</th>
                            <th>상태</th>
                        </tr>
            """
            
            # Add expired products first (if any)
            for alert in expired_products:
                html += f"""
                        <tr class="urgent-row">
                            <td><strong>{alert.get('제품', '')}</strong></td>
                            <td>{alert.get('현재 재고량', 0):,}개</td>
                            <td>{alert.get('소비기한', '')}</td>
                            <td><strong style="color: #d32f2f;">{alert.get('남은 일수', 0)}일</strong></td>
                            <td>🚨 긴급</td>
                        </tr>
                """
            
            # Add non-expired products
            for alert in non_expired_products:
                days_remaining = alert.get('남은 일수', 0)
                
                # Determine row class and emoji based on days remaining (matching app.py logic exactly)
                # app.py logic: <=7 days: 긴급, <=14 days: 경고, <=21 days: 주의, >21 days: no specific status
                if days_remaining <= 7:
                    row_class = "urgent-row"
                    status_emoji = "🚨"
                    status_text = "긴급"
                elif days_remaining <= 14:
                    row_class = "warning-row"
                    status_emoji = "⚠️"
                    status_text = "경고"
                elif days_remaining <= 21:
                    row_class = ""
                    status_emoji = "📋"
                    status_text = "주의"
                else:
                    # More than 21 days - no specific status (monitoring only)
                    row_class = ""
                    status_emoji = ""
                    status_text = ""
                
                # Only show status if it's within the alert threshold
                status_display = f"{status_emoji} {status_text}" if status_text else ""
                
                html += f"""
                        <tr class="{row_class}">
                            <td><strong>{alert.get('제품', '')}</strong></td>
                            <td>{alert.get('현재 재고량', 0):,}개</td>
                            <td>{alert.get('소비기한', '')}</td>
                            <td><strong>{alert.get('남은 일수', 0)}일</strong></td>
                            <td>{status_display}</td>
                        </tr>
                """
            
            html += """
                    </table>
                </div>
            """
        
        # Add summary
        total_urgent = len([a for a in order_alerts if a.get('상태') == '긴급']) + len([a for a in stock_alerts if a.get('상태') == '긴급']) + len([a for a in expiry_alerts if a.get('상태') == '긴급'])
        
        html += f"""
                <div class="alert-section">
                    <h3>📊 요약</h3>
                    <ul>
                        <li>발주 필요: {len(order_alerts)}개 제품</li>
                        <li>재고 부족: {len(stock_alerts)}개 제품</li>
                        <li>소비기한 임박: {len(expiry_alerts)}개 제품</li>
                        <li>긴급 처리 필요: {total_urgent}개 제품</li>
                        <li>총 {len(alerts)}개 제품 주의 필요</li>
                    </ul>
                </div>
                
                <div style="margin-top: 40px; padding: 20px; background-color: #f4f4f4; text-align: center;">
                    <p>이 메일은 PLAYAUTO 시스템에서 자동으로 발송되었습니다.</p>
                    <p><a href="#">PLAYAUTO 시스템 바로가기</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def send_order_reminder(self, recipient_email: str, order_list: List[Dict]) -> bool:
        """Send order reminder email with recommended quantities"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'[PLAYAUTO] 발주 추천 - {datetime.now().strftime("%Y-%m-%d")}'
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            
            # Create HTML content for order list
            html_content = self._create_order_list_html(order_list)
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                
            return True
            
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            return False
    
    def _create_order_list_html(self, order_list: List[Dict]) -> str:
        """Create HTML content for order recommendations"""
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f4f4f4; }}
                .highlight {{ background-color: #e3f2fd; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>발주 추천 리스트</h1>
                <p>{datetime.now().strftime("%Y년 %m월 %d일")}</p>
            </div>
            
            <div class="content">
                <h2>📋 발주 필요 제품</h2>
                <table>
                    <tr>
                        <th>제품명</th>
                        <th>현재 재고</th>
                        <th>권장 발주량</th>
                        <th>MOQ</th>
                        <th>공급업체</th>
                        <th>예상 입고일</th>
                    </tr>
        """
        
        for item in order_list:
            html += f"""
                    <tr class="highlight">
                        <td><strong>{item.get('제품', '')}</strong></td>
                        <td>{item.get('현재 재고', 0):,}개</td>
                        <td><strong>{item.get('권장 발주량', 0):,}개</strong></td>
                        <td>{item.get('MOQ', 0):,}개</td>
                        <td>{item.get('공급업체', '')}</td>
                        <td>{item.get('예상 입고일', '')}</td>
                    </tr>
            """
        
        html += """
                </table>
                
                <div style="margin-top: 30px;">
                    <h3>📌 참고사항</h3>
                    <ul>
                        <li>권장 발주량은 AI 예측과 안전재고를 고려하여 산출되었습니다.</li>
                        <li>MOQ(최소주문수량)을 확인하여 발주해주세요.</li>
                        <li>리드타임을 고려하여 적시에 발주해주세요.</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
