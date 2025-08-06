import schedule
import time
import threading
from datetime import datetime, timedelta
from config.database import ProductQueries, db
from utils.email_alerts import EmailAlertSystem
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class NotificationScheduler:
    def __init__(self):
        self.email_system = EmailAlertSystem()
        self.notification_email = os.getenv('NOTIFICATION_EMAIL', '')
        self.notification_time = os.getenv('NOTIFICATION_TIME', '09:00')
        
        # Default alert thresholds (can be overridden from settings)
        def safe_int_env(key, default):
            val = os.getenv(key, str(default))
            if val:
                # Clean any formatting characters
                val = str(val).replace('│', '').replace('|', '').replace('\n', '').replace('\r', '').strip()
                try:
                    return int(val)
                except:
                    return default
            return default
        
        self.stock_alert_days = safe_int_env('STOCK_ALERT_DAYS', 7)
        self.order_alert_days = safe_int_env('ORDER_ALERT_DAYS', 10)
        self.expiry_alert_days = safe_int_env('EXPIRY_ALERT_DAYS', 30)
        
        self.is_running = False
        self.thread = None
        
    def check_and_send_alerts(self):
        """Check inventory status and send alerts if needed"""
        print(f"[{datetime.now()}] Checking for alerts...")
        
        try:
            alerts_list = []
            products = ProductQueries.get_all_products()
            
            if products:
                for product in products:
                    current_stock = product['현재재고'] or 0
                    safety_stock = product['안전재고'] or 0
                    product_name = product['상품명']
                    lead_time = product['리드타임'] or 30
                    outbound = product['출고량'] or 0
                    expiration = product.get('소비기한')
                    
                    daily_usage = outbound / 30 if outbound > 0 else 0
                    
                    # Check stock depletion
                    if daily_usage > 0:
                        days_until_stockout = current_stock / daily_usage
                        
                        # Stock depletion alert
                        if days_until_stockout <= self.stock_alert_days:
                            stockout_date = (datetime.now() + timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')
                            
                            # Determine status based on how critical the stock level is
                            if current_stock < safety_stock * 0.5:
                                status = '긴급'
                            elif current_stock < safety_stock:
                                status = '경고'
                            else:
                                status = '주의'
                            
                            alerts_list.append({
                                '제품': product_name,
                                '유형': '재고 부족',
                                '현재 재고량': current_stock,
                                '안전재고량': safety_stock,
                                '예상 소진일': stockout_date,
                                '리드타임': lead_time,
                                '상태': status,
                                '메시지': f'{int(days_until_stockout)}일 후 재고 소진 예상'
                            })
                        
                        # Order timing alert - only add if we need to order considering lead time
                        days_until_reorder = days_until_stockout - lead_time
                        if days_until_reorder <= self.order_alert_days and days_until_reorder <= lead_time:
                            # Determine urgency based on how soon we need to order
                            if days_until_reorder <= 0:
                                order_status = '긴급'
                                order_message = '즉시 발주 필요'
                            elif days_until_reorder <= 3:
                                order_status = '경고'
                                order_message = f'{int(days_until_reorder)}일 내 발주 필요'
                            else:
                                order_status = '주의'
                                order_message = f'{int(days_until_reorder)}일 내 발주 권장'
                                
                            alerts_list.append({
                                '제품': product_name,
                                '유형': '발주 시점',
                                '현재 재고량': current_stock,
                                '안전재고량': safety_stock,
                                '예상 소진일': stockout_date,
                                '리드타임': lead_time,
                                '상태': order_status,
                                '메시지': order_message
                            })
                    
                    # Expiration alert
                    if expiration:
                        days_until_expiry = (expiration - datetime.now().date()).days
                        if days_until_expiry <= self.expiry_alert_days:
                            status = '긴급' if days_until_expiry <= 7 else ('경고' if days_until_expiry <= 14 else '주의')
                            
                            alerts_list.append({
                                '제품': product_name,
                                '유형': '소비기한 임박',
                                '현재 재고량': current_stock,
                                '소비기한': expiration.strftime('%Y-%m-%d'),
                                '남은 일수': days_until_expiry,
                                '상태': status,
                                '권장 조치': '판촉 진행 또는 폐기 준비'
                            })
            
            # Send email if there are alerts
            if alerts_list and self.notification_email:
                print(f"Found {len(alerts_list)} alerts. Sending email to {self.notification_email}")
                success = self.email_system.send_inventory_alert(self.notification_email, alerts_list)
                if success:
                    print("Alert email sent successfully")
                else:
                    print("Failed to send alert email")
            else:
                print("No alerts to send")
                
        except Exception as e:
            print(f"Error checking alerts: {str(e)}")
    
    def run_schedule(self):
        """Run the schedule in a separate thread"""
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def start(self):
        """Start the scheduler"""
        if self.is_running:
            print("Scheduler is already running")
            return
        
        # Schedule daily check at specified time
        schedule.every().day.at(self.notification_time).do(self.check_and_send_alerts)
        
        # Optional: Run immediately for testing
        if os.getenv('RUN_IMMEDIATELY', 'false').lower() == 'true':
            self.check_and_send_alerts()
        
        self.is_running = True
        self.thread = threading.Thread(target=self.run_schedule, daemon=True)
        self.thread.start()
        
        print(f"Scheduler started. Will send alerts daily at {self.notification_time}")
        print(f"Alert thresholds - Stock: {self.stock_alert_days} days, Order: {self.order_alert_days} days, Expiry: {self.expiry_alert_days} days")
    
    def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        if self.thread:
            self.thread.join()
        schedule.clear()
        print("Scheduler stopped")

# Main execution
if __name__ == "__main__":
    scheduler = NotificationScheduler()
    
    try:
        scheduler.start()
        
        # Keep the main thread alive
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nShutting down scheduler...")
        scheduler.stop()
