import httpx
import json
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import settings


class EventService:
    def __init__(self):
        self.websocket_service_url = os.getenv("WEBSOCKET_SERVICE_URL", "http://websocket-service:8012")

    async def publish_payment_event(self, event_type: str, payment_data: Dict[str, Any], user_id: str):
        """Publish payment-related events to the event system."""
        event_data = {
            "event_type": f"payment.{event_type}",
            "data": payment_data,
            "user_id": user_id,
            "service": "payment-service"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.websocket_service_url}/events/publish",
                    json=event_data,
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to publish event: {e}")
            return False

    async def notify_order_service(self, event_type: str, payment_data: Dict[str, Any]):
        """Notify order service about payment events."""
        order_service_url = os.getenv("ORDER_SERVICE_URL", "http://order-service:8005")
        
        event_data = {
            "event_type": event_type,
            "payment_data": payment_data
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{order_service_url}/webhooks/payment",
                    json=event_data,
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to notify order service: {e}")
            return False

    async def send_notification(self, user_id: str, notification_type: str, title: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Send notification to user."""
        notification_service_url = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8010")
        
        notification_data = {
            "user_id": user_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "data": data or {}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{notification_service_url}/notifications/send",
                    json=notification_data,
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to send notification: {e}")
            return False
