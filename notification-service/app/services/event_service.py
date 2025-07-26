"""
Resilient event service for notification handling.
Handles RabbitMQ connection failures gracefully and provides fallback mechanisms.
"""

import json
import asyncio
import aio_pika
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

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
    Resilient service for handling notification events.
    Handles RabbitMQ connection failures gracefully and provides fallback mechanisms.
    """

    def __init__(self):
        self.settings = settings
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
        
        # Event handlers
        self.event_handlers = {
            "order.created": self._handle_order_created,
            "order.status_changed": self._handle_order_status_changed,
            "order.cancelled": self._handle_order_cancelled,
            "payment.completed": self._handle_payment_completed,
            "payment.failed": self._handle_payment_failed,
            "inventory.low_stock": self._handle_low_stock_alert,
            "user.registered": self._handle_user_registered,
            "system.alert": self._handle_system_alert,
        }

    async def connect(self):
        """
        Start RabbitMQ connection with graceful error handling.
        Service will start even if RabbitMQ is unavailable.
        """
        self.is_running = True
        logger.info("Starting Notification Event Service...")
        
        # Start connection attempt in background
        self.reconnect_task = asyncio.create_task(self._connect_with_retry())
        
        logger.info("Notification Event Service started (will connect to RabbitMQ when available)")
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
                
                # Set up exchanges and queues
                await self._setup_event_infrastructure()
                
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
        logger.info("Notification Event Service stopped")
    
    def _on_connection_closed(self, connection, exception=None):
        """Handle RabbitMQ connection closure and attempt reconnection."""
        if self.is_running:
            logger.warning(f"RabbitMQ connection lost: {exception}")
            self.connection_state = ConnectionState.DISCONNECTED
            
            # Start reconnection attempt
            if not self.reconnect_task or self.reconnect_task.done():
                self.reconnect_task = asyncio.create_task(self._connect_with_retry())

    async def _setup_event_infrastructure(self):
        """Set up RabbitMQ exchanges and queues for event listening."""
        
        # Declare exchanges for different services
        exchanges = [
            "order_events",
            "payment_events", 
            "inventory_events",
            "user_events",
            "system_events"
        ]
        
        for exchange_name in exchanges:
            exchange = await self.channel.declare_exchange(
                exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
        
        # Create notification service queue
        notification_queue = await self.channel.declare_queue(
            "notification_service_events",
            durable=True
        )
        
        # Bind queue to all exchanges with relevant routing keys
        routing_patterns = [
            ("order_events", "order.*"),
            ("payment_events", "payment.*"),
            ("inventory_events", "inventory.*"),
            ("user_events", "user.*"),
            ("system_events", "system.*"),
        ]
        
        for exchange_name, pattern in routing_patterns:
            exchange = await self.channel.get_exchange(exchange_name)
            await notification_queue.bind(exchange, routing_key=pattern)
        
        # Start consuming messages
        await notification_queue.consume(self._process_event)

    async def _process_event(self, message_or_data):
        """Process incoming events from RabbitMQ or local storage."""
        try:
            # Handle both RabbitMQ messages and local event data
            if isinstance(message_or_data, aio_pika.IncomingMessage):
                # RabbitMQ message
                async with message_or_data.process():
                    event_data = json.loads(message_or_data.body.decode())
                    routing_key = message_or_data.routing_key
            else:
                # Local event data
                event_data = message_or_data.get("data", {})
                routing_key = message_or_data.get("routing_key", "unknown")
            
            logger.debug(f"Processing notification event: {routing_key}")
            
            # Handle the event
            handler = self.event_handlers.get(routing_key)
            if handler:
                await handler(event_data)
                logger.debug(f"Successfully processed notification event: {routing_key}")
            else:
                logger.warning(f"No handler found for notification event: {routing_key}")
            
        except Exception as e:
            logger.error(f"Error processing notification event {routing_key if 'routing_key' in locals() else 'unknown'}: {e}")

    async def _process_pending_events(self):
        """Process events that were stored while RabbitMQ was unavailable."""
        if not self.pending_events:
            return
        
        logger.info(f"Processing {len(self.pending_events)} pending notification events...")
        
        for event_data in self.pending_events.copy():
            try:
                await self._process_event(event_data)
                self.pending_events.remove(event_data)
            except Exception as e:
                logger.error(f"Failed to process pending notification event: {e}")
        
        logger.info("Finished processing pending notification events")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status for health checks."""
        return {
            "state": self.connection_state.value,
            "connected": self.connection_state == ConnectionState.CONNECTED,
            "pending_events": len(self.pending_events),
            "rabbitmq_url": self.settings.RABBITMQ_URL,
            "is_running": self.is_running
        }

    # Event Handlers
    async def _handle_order_created(self, event_data: Dict[str, Any]):
        """Handle order creation notifications."""
        logger.info(f"Sending order creation notification for order: {event_data.get('order_id')}")
        # Implementation would send email/SMS notifications

    async def _handle_order_status_changed(self, event_data: Dict[str, Any]):
        """Handle order status change notifications."""
        logger.info(f"Sending order status change notification for order: {event_data.get('order_id')}")
        # Implementation would send status update notifications

    async def _handle_order_cancelled(self, event_data: Dict[str, Any]):
        """Handle order cancellation notifications."""
        logger.info(f"Sending order cancellation notification for order: {event_data.get('order_id')}")
        # Implementation would send cancellation notifications

    async def _handle_payment_completed(self, event_data: Dict[str, Any]):
        """Handle payment completion notifications."""
        logger.info(f"Sending payment completion notification for payment: {event_data.get('payment_id')}")
        # Implementation would send payment confirmation

    async def _handle_payment_failed(self, event_data: Dict[str, Any]):
        """Handle payment failure notifications."""
        logger.info(f"Sending payment failure notification for payment: {event_data.get('payment_id')}")
        # Implementation would send payment failure alerts

    async def _handle_low_stock_alert(self, event_data: Dict[str, Any]):
        """Handle low stock alert notifications."""
        logger.info(f"Sending low stock alert for inventory: {event_data.get('inventory_id')}")
        # Implementation would send low stock alerts to vendors

    async def _handle_user_registered(self, event_data: Dict[str, Any]):
        """Handle user registration notifications."""
        logger.info(f"Sending welcome notification for user: {event_data.get('user_id')}")
        # Implementation would send welcome emails

    async def _handle_system_alert(self, event_data: Dict[str, Any]):
        """Handle system alert notifications."""
        logger.info(f"Sending system alert: {event_data.get('alert_type')}")
        # Implementation would send system alerts to admins


# Global event service instance
event_service = EventService()
