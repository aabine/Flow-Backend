import json
import asyncio
import aio_pika
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from shared.models import EventType

settings = get_settings()


class EventService:
    """Service for handling events and notifications."""

    def __init__(self):
        self.settings = settings
        self.connection = None
        self.channel = None
        self.exchange = None
        self.event_queue = asyncio.Queue()

    async def connect(self):
        """Connect to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(self.settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()

            # Declare exchange for inventory events
            self.exchange = await self.channel.declare_exchange(
                "inventory_events",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # Set up order event listener
            await self._setup_order_event_listener()

        except Exception as e:
            print(f"Failed to connect to RabbitMQ: {e}")

    async def disconnect(self):
        """Disconnect from RabbitMQ."""
        if self.connection:
            await self.connection.close()

    async def _setup_order_event_listener(self):
        """Set up listener for order events to handle stock deduction."""
        try:
            # Declare queue for order events
            order_queue = await self.channel.declare_queue(
                "inventory_order_events",
                durable=True
            )

            # Get order events exchange
            order_exchange = await self.channel.declare_exchange(
                "order_events",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # Bind to order events we care about
            await order_queue.bind(order_exchange, routing_key="order.confirmed")
            await order_queue.bind(order_exchange, routing_key="order.cancelled")
            await order_queue.bind(order_exchange, routing_key="order.completed")

            # Start consuming
            await order_queue.consume(self._handle_order_event)

        except Exception as e:
            print(f"Failed to set up order event listener: {e}")

    async def _handle_order_event(self, message: aio_pika.IncomingMessage):
        """Handle incoming order events."""
        async with message.process():
            try:
                event_data = json.loads(message.body.decode())
                routing_key = message.routing_key

                if routing_key == "order.confirmed":
                    await self._handle_order_confirmed(event_data)
                elif routing_key == "order.cancelled":
                    await self._handle_order_cancelled(event_data)
                elif routing_key == "order.completed":
                    await self._handle_order_completed(event_data)

            except Exception as e:
                print(f"Error handling order event: {e}")

    async def _handle_order_confirmed(self, event_data: Dict[str, Any]):
        """Handle order confirmation - deduct reserved stock."""
        try:
            # This would trigger stock deduction from reservations
            print(f"Processing order confirmation: {event_data.get('order_id')}")
            # Implementation would call inventory service to confirm reservations

        except Exception as e:
            print(f"Error handling order confirmation: {e}")

    async def _handle_order_cancelled(self, event_data: Dict[str, Any]):
        """Handle order cancellation - release reserved stock."""
        try:
            # This would trigger stock release from reservations
            print(f"Processing order cancellation: {event_data.get('order_id')}")
            # Implementation would call inventory service to cancel reservations

        except Exception as e:
            print(f"Error handling order cancellation: {e}")

    async def _handle_order_completed(self, event_data: Dict[str, Any]):
        """Handle order completion - finalize stock movement."""
        try:
            # This would finalize the stock movement
            print(f"Processing order completion: {event_data.get('order_id')}")

        except Exception as e:
            print(f"Error handling order completion: {e}")
    
    async def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_service: str = "inventory-service"
    ) -> bool:
        """Publish an event to the event system."""
        try:
            event = {
                "id": f"evt_{datetime.utcnow().timestamp()}",
                "event_type": event_type.value,
                "source_service": source_service,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
                "processed": False
            }

            # Publish to RabbitMQ if connected
            if self.exchange:
                await self._publish_to_rabbitmq(event_type.value, event)
            else:
                # Fallback to local queue
                await self.event_queue.put(event)

            print(f"Event published: {event_type.value} from {source_service}")
            return True

        except Exception as e:
            print(f"Failed to publish event: {str(e)}")
            return False

    async def _publish_to_rabbitmq(self, routing_key: str, event_data: Dict[str, Any]):
        """Publish event to RabbitMQ."""
        try:
            message = aio_pika.Message(
                json.dumps(event_data).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.exchange.publish(message, routing_key=routing_key)

        except Exception as e:
            print(f"Failed to publish to RabbitMQ: {e}")
            # Fallback to local queue
            await self.event_queue.put(event_data)
    
    async def publish_inventory_updated(
        self,
        inventory_id: str,
        vendor_id: str,
        cylinder_size: str,
        quantity_change: int,
        new_quantity: int
    ):
        """Publish inventory updated event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "cylinder_size": cylinder_size,
                "quantity_change": quantity_change,
                "new_quantity": new_quantity
            }
        )
    
    async def publish_low_stock_alert(
        self,
        inventory_id: str,
        vendor_id: str,
        cylinder_size: str,
        current_quantity: int,
        minimum_threshold: int
    ):
        """Publish low stock alert event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,  # Using existing event type
            {
                "alert_type": "low_stock",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "cylinder_size": cylinder_size,
                "current_quantity": current_quantity,
                "minimum_threshold": minimum_threshold
            }
        )
    
    async def publish_stock_reserved(
        self,
        inventory_id: str,
        vendor_id: str,
        order_id: str,
        cylinder_size: str,
        quantity: int
    ):
        """Publish stock reserved event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "action": "stock_reserved",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "order_id": order_id,
                "cylinder_size": cylinder_size,
                "quantity": quantity
            }
        )
    
    async def publish_stock_released(
        self,
        inventory_id: str,
        vendor_id: str,
        order_id: str,
        cylinder_size: str,
        quantity: int
    ):
        """Publish stock released event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "action": "stock_released",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "order_id": order_id,
                "cylinder_size": cylinder_size,
                "quantity": quantity
            }
        )
    
    async def process_events(self):
        """Process events from the queue (background task)."""
        while True:
            try:
                event = await self.event_queue.get()
                # In a real implementation, this would send to message broker
                print(f"Processing event: {json.dumps(event, indent=2)}")
                self.event_queue.task_done()
            except Exception as e:
                print(f"Error processing event: {str(e)}")
                await asyncio.sleep(1)

    async def emit_inventory_created(self, inventory_data: Dict[str, Any]):
        """Emit event when inventory is created."""
        event_data = {
            "event_type": "inventory_created",
            "inventory_id": inventory_data.get("inventory_id"),
            "vendor_id": inventory_data.get("vendor_id"),
            "cylinder_size": inventory_data.get("cylinder_size"),
            "quantity": inventory_data.get("quantity"),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self._publish_to_rabbitmq("inventory.created", event_data)

    async def emit_stock_updated(self, stock_data: Dict[str, Any]):
        """Emit event when stock is updated."""
        event_data = {
            "event_type": "stock_updated",
            "inventory_id": stock_data.get("inventory_id"),
            "vendor_id": stock_data.get("vendor_id"),
            "old_quantity": stock_data.get("old_quantity"),
            "new_quantity": stock_data.get("new_quantity"),
            "change_type": stock_data.get("change_type"),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self._publish_to_rabbitmq("inventory.stock_updated", event_data)

    async def emit_reservation_created(self, reservation_data: Dict[str, Any]):
        """Emit event when reservation is created."""
        event_data = {
            "event_type": "reservation_created",
            "reservation_id": reservation_data.get("reservation_id"),
            "inventory_id": reservation_data.get("inventory_id"),
            "order_id": reservation_data.get("order_id"),
            "quantity": reservation_data.get("quantity"),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self._publish_to_rabbitmq("inventory.reservation_created", event_data)

    async def emit_low_stock_alert(self, alert_data: Dict[str, Any]):
        """Emit low stock alert event."""
        event_data = {
            "event_type": "low_stock_alert",
            "inventory_id": alert_data.get("inventory_id"),
            "vendor_id": alert_data.get("vendor_id"),
            "cylinder_size": alert_data.get("cylinder_size"),
            "current_quantity": alert_data.get("current_quantity"),
            "threshold": alert_data.get("threshold"),
            "severity": alert_data.get("severity", "medium"),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self._publish_to_rabbitmq("inventory.low_stock_alert", event_data)


# Global event service instance
event_service = EventService()
