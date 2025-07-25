"""
Resilient event service for delivery handling.
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
    Resilient service for handling delivery events.
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
            "order.confirmed": self._handle_order_confirmed,
            "order.cancelled": self._handle_order_cancelled,
            "delivery.assigned": self._handle_delivery_assigned,
            "delivery.started": self._handle_delivery_started,
            "delivery.completed": self._handle_delivery_completed,
            "driver.location_updated": self._handle_driver_location_updated,
        }

    async def connect(self):
        """
        Start RabbitMQ connection with graceful error handling.
        Service will start even if RabbitMQ is unavailable.
        """
        self.is_running = True
        logger.info("Starting Delivery Event Service...")
        
        # Start connection attempt in background
        self.reconnect_task = asyncio.create_task(self._connect_with_retry())
        
        logger.info("Delivery Event Service started (will connect to RabbitMQ when available)")
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
                self.connection.add_close_callback(self._on_connection_closed)
                
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
        logger.info("Delivery Event Service stopped")
    
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
        
        # Declare exchange for delivery events
        self.exchange = await self.channel.declare_exchange(
            "delivery_events",
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        
        # Create delivery service queue
        delivery_queue = await self.channel.declare_queue(
            "delivery_service_events",
            durable=True
        )
        
        # Bind queue to relevant exchanges
        exchanges_and_patterns = [
            ("order_events", "order.*"),
            ("delivery_events", "delivery.*"),
            ("driver_events", "driver.*"),
        ]
        
        for exchange_name, pattern in exchanges_and_patterns:
            try:
                exchange = await self.channel.declare_exchange(
                    exchange_name,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )
                await delivery_queue.bind(exchange, routing_key=pattern)
            except Exception as e:
                logger.warning(f"Failed to bind to exchange {exchange_name}: {e}")
        
        # Start consuming messages
        await delivery_queue.consume(self._process_event)

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
            
            logger.debug(f"Processing delivery event: {routing_key}")
            
            # Handle the event
            handler = self.event_handlers.get(routing_key)
            if handler:
                await handler(event_data)
                logger.debug(f"Successfully processed delivery event: {routing_key}")
            else:
                logger.warning(f"No handler found for delivery event: {routing_key}")
            
        except Exception as e:
            logger.error(f"Error processing delivery event {routing_key if 'routing_key' in locals() else 'unknown'}: {e}")

    async def _process_pending_events(self):
        """Process events that were stored while RabbitMQ was unavailable."""
        if not self.pending_events:
            return
        
        logger.info(f"Processing {len(self.pending_events)} pending delivery events...")
        
        for event_data in self.pending_events.copy():
            try:
                await self._process_event(event_data)
                self.pending_events.remove(event_data)
            except Exception as e:
                logger.error(f"Failed to process pending delivery event: {e}")
        
        logger.info("Finished processing pending delivery events")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status for health checks."""
        return {
            "state": self.connection_state.value,
            "connected": self.connection_state == ConnectionState.CONNECTED,
            "pending_events": len(self.pending_events),
            "rabbitmq_url": self.settings.RABBITMQ_URL,
            "is_running": self.is_running
        }

    async def publish_delivery_event(self, routing_key: str, event_data: Dict[str, Any]):
        """Publish delivery event with fallback to local storage."""
        if self.connection_state == ConnectionState.CONNECTED and self.exchange:
            try:
                message = aio_pika.Message(
                    json.dumps(event_data).encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                )

                await self.exchange.publish(message, routing_key=routing_key)
                logger.debug(f"Published delivery event {routing_key} to RabbitMQ")
                return

            except Exception as e:
                logger.warning(f"Failed to publish delivery event to RabbitMQ: {e}")
        
        # Fallback: store event locally
        if len(self.pending_events) < self.max_pending_events:
            self.pending_events.append({
                "routing_key": routing_key,
                "data": event_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.debug(f"Stored delivery event {routing_key} locally (RabbitMQ unavailable)")
        else:
            logger.warning(f"Pending events buffer full, dropping delivery event {routing_key}")

    # Event Handlers
    async def _handle_order_created(self, event_data: Dict[str, Any]):
        """Handle order creation for delivery assignment."""
        logger.info(f"Processing order creation for delivery: {event_data.get('order_id')}")
        # Implementation would handle delivery assignment logic

    async def _handle_order_confirmed(self, event_data: Dict[str, Any]):
        """Handle order confirmation for delivery preparation."""
        logger.info(f"Processing order confirmation for delivery: {event_data.get('order_id')}")
        # Implementation would prepare delivery

    async def _handle_order_cancelled(self, event_data: Dict[str, Any]):
        """Handle order cancellation for delivery cancellation."""
        logger.info(f"Processing order cancellation for delivery: {event_data.get('order_id')}")
        # Implementation would cancel delivery

    async def _handle_delivery_assigned(self, event_data: Dict[str, Any]):
        """Handle delivery assignment notifications."""
        logger.info(f"Processing delivery assignment: {event_data.get('delivery_id')}")
        # Implementation would notify driver and customer

    async def _handle_delivery_started(self, event_data: Dict[str, Any]):
        """Handle delivery start notifications."""
        logger.info(f"Processing delivery start: {event_data.get('delivery_id')}")
        # Implementation would start tracking

    async def _handle_delivery_completed(self, event_data: Dict[str, Any]):
        """Handle delivery completion notifications."""
        logger.info(f"Processing delivery completion: {event_data.get('delivery_id')}")
        # Implementation would finalize delivery

    async def _handle_driver_location_updated(self, event_data: Dict[str, Any]):
        """Handle driver location updates."""
        logger.debug(f"Processing driver location update: {event_data.get('driver_id')}")
        # Implementation would update tracking


# Global event service instance
event_service = EventService()
