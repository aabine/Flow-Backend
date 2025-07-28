import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aio_pika
from aio_pika import Message, DeliveryMode
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EventService:
    """Service for handling message queue events and notifications."""
    
    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        
    async def connect(self):
        """Connect to RabbitMQ message broker."""
        try:
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()
            
            # Declare exchange for pricing events
            self.exchange = await self.channel.declare_exchange(
                "pricing_events",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Declare queues for different event types
            await self._declare_queues()
            
            logger.info("✅ Connected to RabbitMQ for pricing events")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            logger.info("✅ Disconnected from RabbitMQ")
        except Exception as e:
            logger.error(f"❌ Error disconnecting from RabbitMQ: {e}")
    
    async def _declare_queues(self):
        """Declare queues for different event types."""
        queues = [
            "pricing.price_updated",
            "pricing.vendor_added",
            "pricing.product_added",
            "pricing.availability_changed",
            "pricing.price_alert_triggered"
        ]
        
        for queue_name in queues:
            queue = await self.channel.declare_queue(queue_name, durable=True)
            await queue.bind(self.exchange, routing_key=queue_name)
    
    async def publish_price_update(self, vendor_id: str, product_id: str, 
                                 old_price: float, new_price: float, 
                                 pricing_tier_id: str):
        """Publish price update event."""
        event_data = {
            "event_type": "price_updated",
            "vendor_id": vendor_id,
            "product_id": product_id,
            "pricing_tier_id": pricing_tier_id,
            "old_price": float(old_price),
            "new_price": float(new_price),
            "change_percentage": ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._publish_event("pricing.price_updated", event_data)
        logger.info(f"Published price update event for product {product_id}")
    
    async def publish_vendor_added(self, vendor_id: str, vendor_data: Dict[str, Any]):
        """Publish new vendor event."""
        event_data = {
            "event_type": "vendor_added",
            "vendor_id": vendor_id,
            "business_name": vendor_data.get("business_name"),
            "business_type": vendor_data.get("business_type"),
            "location": {
                "city": vendor_data.get("business_city"),
                "state": vendor_data.get("business_state"),
                "country": vendor_data.get("business_country")
            },
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._publish_event("pricing.vendor_added", event_data)
        logger.info(f"Published vendor added event for vendor {vendor_id}")
    
    async def publish_product_added(self, vendor_id: str, product_id: str, 
                                  product_data: Dict[str, Any]):
        """Publish new product event."""
        event_data = {
            "event_type": "product_added",
            "vendor_id": vendor_id,
            "product_id": product_id,
            "product_name": product_data.get("product_name"),
            "product_category": product_data.get("product_category"),
            "cylinder_size": product_data.get("cylinder_size"),
            "base_price": float(product_data.get("base_price", 0)),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._publish_event("pricing.product_added", event_data)
        logger.info(f"Published product added event for product {product_id}")
    
    async def publish_availability_changed(self, vendor_id: str, product_id: str,
                                         old_quantity: int, new_quantity: int):
        """Publish availability change event."""
        event_data = {
            "event_type": "availability_changed",
            "vendor_id": vendor_id,
            "product_id": product_id,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "is_available": new_quantity > 0,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._publish_event("pricing.availability_changed", event_data)
        logger.info(f"Published availability change event for product {product_id}")
    
    async def publish_price_alert_triggered(self, user_id: str, alert_id: str,
                                          product_id: str, vendor_id: str,
                                          current_price: float, target_price: float):
        """Publish price alert triggered event."""
        event_data = {
            "event_type": "price_alert_triggered",
            "user_id": user_id,
            "alert_id": alert_id,
            "product_id": product_id,
            "vendor_id": vendor_id,
            "current_price": float(current_price),
            "target_price": float(target_price),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self._publish_event("pricing.price_alert_triggered", event_data)
        logger.info(f"Published price alert triggered event for user {user_id}")
    
    async def _publish_event(self, routing_key: str, event_data: Dict[str, Any]):
        """Publish event to message queue."""
        try:
            if not self.exchange:
                logger.warning("Exchange not initialized, skipping event publication")
                return
            
            message = Message(
                json.dumps(event_data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json"
            )
            
            await self.exchange.publish(message, routing_key=routing_key)
            
        except Exception as e:
            logger.error(f"Failed to publish event {routing_key}: {e}")


# Global event service instance
event_service = EventService()
