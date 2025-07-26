import httpx
import asyncio
import aio_pika
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import EventType, OrderStatus
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """RabbitMQ connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class EventService:
    """
    Resilient service for handling order-related events and notifications.
    Handles RabbitMQ connection failures gracefully and provides fallback mechanisms.
    """

    def __init__(self):
        self.settings = settings
        self.websocket_service_url = "http://websocket-service:8012"
        self.event_queue = asyncio.Queue()

        # RabbitMQ connection management
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.reconnect_task: Optional[asyncio.Task] = None
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.is_running = False

        # Event buffering for offline scenarios
        self.pending_events = []
        self.max_pending_events = 1000

    async def connect(self):
        """
        Start RabbitMQ connection with graceful error handling.
        Service will start even if RabbitMQ is unavailable.
        """
        self.is_running = True
        logger.info("Starting Order Event Service...")

        # Start connection attempt in background
        self.reconnect_task = asyncio.create_task(self._connect_with_retry())

        logger.info("Order Event Service started (will connect to RabbitMQ when available)")
        return True  # Always return success to allow service to start

    async def _connect_with_retry(self):
        """Attempt to connect to RabbitMQ with exponential backoff."""
        retry_count = 0

        while self.is_running and retry_count < self.max_retries:
            try:
                self.connection_state = ConnectionState.CONNECTING
                logger.info(f"Attempting to connect to RabbitMQ (attempt {retry_count + 1}/{self.max_retries})")

                # Try to connect to RabbitMQ
                self.connection = await aio_pika.connect_robust(
                    self.settings.RABBITMQ_URL,
                    timeout=10.0
                )
                self.channel = await self.connection.channel()

                # Declare exchange for order events
                self.exchange = await self.channel.declare_exchange(
                    "order_events",
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )

                self.connection_state = ConnectionState.CONNECTED
                logger.info("✅ Successfully connected to RabbitMQ and set up event infrastructure")

                # Process any pending events
                await self._process_pending_events()

                # Set up connection close callback for automatic reconnection
                try:
                    if hasattr(self.connection, 'add_close_callback'):
                        self.connection.add_close_callback(self._on_connection_closed)
                    elif hasattr(self.connection, 'close_callbacks'):
                        self.connection.close_callbacks.add(self._on_connection_closed)
                    else:
                        logger.warning("Connection close callback not supported in this aio_pika version")
                except Exception as e:
                    logger.warning(f"Failed to set up connection close callback: {e}")

                return  # Success, exit retry loop

            except Exception as e:
                retry_count += 1
                self.connection_state = ConnectionState.FAILED

                if retry_count < self.max_retries:
                    delay = min(self.retry_delay * (2 ** retry_count), 60)  # Exponential backoff, max 60s
                    logger.warning(f"❌ Failed to connect to RabbitMQ: {e}. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Failed to connect to RabbitMQ after {self.max_retries} attempts: {e}")
                    logger.info("📝 Service will continue without RabbitMQ. Events will be stored locally.")

        # If we reach here, all retries failed
        self.connection_state = ConnectionState.FAILED

    async def disconnect(self):
        """Stop listening to events and close connections."""
        self.is_running = False

        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        if self.connection and not self.connection.is_closed:
            await self.connection.close()

        self.connection_state = ConnectionState.DISCONNECTED
        logger.info("Order Event Service stopped")

    def _on_connection_closed(self, connection, exception=None):
        """Handle RabbitMQ connection closure and attempt reconnection."""
        if self.is_running:
            logger.warning(f"RabbitMQ connection lost: {exception}")
            self.connection_state = ConnectionState.DISCONNECTED

            # Start reconnection attempt
            if not self.reconnect_task or self.reconnect_task.done():
                self.reconnect_task = asyncio.create_task(self._connect_with_retry())

    async def _process_pending_events(self):
        """Process events that were stored while RabbitMQ was unavailable."""
        if not self.pending_events:
            return

        logger.info(f"Processing {len(self.pending_events)} pending events...")

        for event_data in self.pending_events.copy():
            try:
                await self._publish_to_rabbitmq(event_data.get("routing_key", "unknown"), event_data)
                self.pending_events.remove(event_data)
            except Exception as e:
                logger.error(f"Failed to process pending event: {e}")

        logger.info("Finished processing pending events")

    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status for health checks."""
        return {
            "state": self.connection_state.value,
            "connected": self.connection_state == ConnectionState.CONNECTED,
            "pending_events": len(self.pending_events),
            "rabbitmq_url": self.settings.RABBITMQ_URL,
            "is_running": self.is_running
        }

    async def _publish_to_rabbitmq(self, routing_key: str, event_data: Dict[str, Any]):
        """Publish event to RabbitMQ with fallback to local storage."""
        if self.connection_state == ConnectionState.CONNECTED and self.exchange:
            try:
                message = aio_pika.Message(
                    json.dumps(event_data).encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                )

                await self.exchange.publish(message, routing_key=routing_key)
                logger.debug(f"Published event {routing_key} to RabbitMQ")
                return

            except Exception as e:
                logger.warning(f"Failed to publish to RabbitMQ: {e}")

        # Fallback: store event locally
        if len(self.pending_events) < self.max_pending_events:
            self.pending_events.append({
                "routing_key": routing_key,
                "data": event_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.debug(f"Stored event {routing_key} locally (RabbitMQ unavailable)")
        else:
            logger.warning(f"Pending events buffer full, dropping event {routing_key}")
            # Fallback to local queue for processing
            await self.event_queue.put(event_data)

    async def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_service: str = "order-service"
    ) -> bool:
        """Publish an event to the event system with RabbitMQ support."""
        try:
            event = {
                "id": f"evt_{datetime.utcnow().timestamp()}",
                "event_type": event_type.value,
                "source_service": source_service,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
                "processed": False
            }

            # Try to publish to RabbitMQ first
            await self._publish_to_rabbitmq(event_type.value, event)

            # Also add to local queue for processing
            await self.event_queue.put(event)

            logger.debug(f"Event published: {event_type.value} from {source_service}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish event: {str(e)}")
            return False
    
    async def emit_order_created(self, order_id: str, hospital_id: str, vendor_id: str, 
                               order_data: dict):
        """Emit order creation event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/order-created",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "vendor_id": vendor_id,
                        "order_data": order_data,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Failed to emit order creation event: {e}")
    
    async def emit_order_status_changed(self, order_id: str, hospital_id: str, vendor_id: str, 
                                      status: OrderStatus, estimated_delivery: Optional[str] = None,
                                      tracking_info: Optional[dict] = None):
        """Emit order status change event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/order-status",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "vendor_id": vendor_id,
                        "status": status,
                        "estimated_delivery": estimated_delivery,
                        "tracking_info": tracking_info,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Failed to emit order status change: {e}")
    
    async def emit_order_accepted(self, order_id: str, hospital_id: str, vendor_id: str,
                                estimated_delivery: Optional[str] = None):
        """Emit order acceptance event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/order-accepted",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "vendor_id": vendor_id,
                        "estimated_delivery": estimated_delivery,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Failed to emit order acceptance event: {e}")
    
    async def emit_order_cancelled(self, order_id: str, hospital_id: str, vendor_id: str,
                                 reason: Optional[str] = None):
        """Emit order cancellation event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/order-cancelled",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "vendor_id": vendor_id,
                        "reason": reason,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Failed to emit order cancellation event: {e}")
    
    async def emit_emergency_order_created(self, order_id: str, hospital_id: str, 
                                         order_data: dict):
        """Emit emergency order creation event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/emergency-order",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "order_data": order_data,
                        "priority": "emergency",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Failed to emit emergency order event: {e}")
    
    async def publish_order_created(self, order_id: str, hospital_id: str, vendor_id: str,
                                  order_data: dict):
        """Publish order creation event."""
        await self.publish_event(
            EventType.ORDER_CREATED,
            {
                "order_id": order_id,
                "hospital_id": hospital_id,
                "vendor_id": vendor_id,
                "order_data": order_data
            }
        )
        await self.emit_order_created(order_id, hospital_id, vendor_id, order_data)
    
    async def publish_order_status_changed(self, order_id: str, hospital_id: str, 
                                         vendor_id: str, old_status: OrderStatus,
                                         new_status: OrderStatus, **kwargs):
        """Publish order status change event."""
        await self.publish_event(
            EventType.ORDER_STATUS_CHANGED,
            {
                "order_id": order_id,
                "hospital_id": hospital_id,
                "vendor_id": vendor_id,
                "old_status": old_status,
                "new_status": new_status,
                **kwargs
            }
        )
        await self.emit_order_status_changed(
            order_id, hospital_id, vendor_id, new_status, 
            kwargs.get("estimated_delivery"), kwargs.get("tracking_info")
        )
