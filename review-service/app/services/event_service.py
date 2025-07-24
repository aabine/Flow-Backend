import json
import aio_pika
from typing import Dict, Any
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from shared.models import EventType

settings = get_settings()


class EventService:
    def __init__(self):
        self.settings = settings
        self.connection = None
        self.channel = None

    async def connect(self):
        """Connect to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(self.settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()
            
            # Declare exchange for review events
            self.exchange = await self.channel.declare_exchange(
                "review_events", 
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
        except Exception as e:
            print(f"Failed to connect to RabbitMQ: {e}")

    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        if self.connection:
            await self.connection.close()

    async def emit_review_created(self, review_data: Dict[str, Any]):
        """Emit event when a review is created."""
        event_data = {
            "event_type": "review_created",
            "review_id": review_data.get("id"),
            "order_id": review_data.get("order_id"),
            "reviewer_id": review_data.get("reviewer_id"),
            "reviewee_id": review_data.get("reviewee_id"),
            "rating": review_data.get("rating"),
            "review_type": review_data.get("review_type"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_event("review.created", event_data)

    async def emit_review_updated(self, review_data: Dict[str, Any]):
        """Emit event when a review is updated."""
        event_data = {
            "event_type": "review_updated",
            "review_id": review_data.get("id"),
            "order_id": review_data.get("order_id"),
            "reviewer_id": review_data.get("reviewer_id"),
            "reviewee_id": review_data.get("reviewee_id"),
            "rating": review_data.get("rating"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_event("review.updated", event_data)

    async def emit_review_responded(self, review_data: Dict[str, Any]):
        """Emit event when a review receives a response."""
        event_data = {
            "event_type": "review_responded",
            "review_id": review_data.get("id"),
            "order_id": review_data.get("order_id"),
            "reviewer_id": review_data.get("reviewer_id"),
            "reviewee_id": review_data.get("reviewee_id"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_event("review.responded", event_data)

    async def emit_review_reported(self, review_data: Dict[str, Any], report_data: Dict[str, Any]):
        """Emit event when a review is reported."""
        event_data = {
            "event_type": "review_reported",
            "review_id": review_data.get("id"),
            "report_id": report_data.get("id"),
            "reporter_id": report_data.get("reporter_id"),
            "reason": report_data.get("reason"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_event("review.reported", event_data)

    async def emit_review_moderated(self, review_data: Dict[str, Any], action: str):
        """Emit event when a review is moderated."""
        event_data = {
            "event_type": "review_moderated",
            "review_id": review_data.get("id"),
            "action": action,
            "status": review_data.get("status"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_event("review.moderated", event_data)

    async def _publish_event(self, routing_key: str, event_data: Dict[str, Any]):
        """Publish event to RabbitMQ."""
        if not self.channel:
            await self.connect()
        
        try:
            message = aio_pika.Message(
                json.dumps(event_data).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await self.exchange.publish(message, routing_key=routing_key)
            print(f"Published event: {routing_key}")
            
        except Exception as e:
            print(f"Failed to publish event {routing_key}: {e}")


# Global event service instance
event_service = EventService()
