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
from shared.models import EventType

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
    Resilient service for handling review events.
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

    async def connect(self):
        """
        Start RabbitMQ connection with graceful error handling.
        Service will start even if RabbitMQ is unavailable.
        """
        self.is_running = True
        logger.info("Starting Review Event Service...")

        # Start connection attempt in background
        self.reconnect_task = asyncio.create_task(self._connect_with_retry())

        logger.info("Review Event Service started (will connect to RabbitMQ when available)")
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

                # Declare exchange for review events
                self.exchange = await self.channel.declare_exchange(
                    "review_events",
                    aio_pika.ExchangeType.TOPIC,
                    durable=True
                )

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
        logger.info("Review Event Service stopped")

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
        
        await self._publish_to_rabbitmq("review.created", event_data)

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
        
        await self._publish_to_rabbitmq("review.updated", event_data)

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
        
        await self._publish_to_rabbitmq("review.responded", event_data)

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
        
        await self._publish_to_rabbitmq("review.reported", event_data)

    async def emit_review_moderated(self, review_data: Dict[str, Any], action: str):
        """Emit event when a review is moderated."""
        event_data = {
            "event_type": "review_moderated",
            "review_id": review_data.get("id"),
            "action": action,
            "status": review_data.get("status"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._publish_to_rabbitmq("review.moderated", event_data)




# Global event service instance
event_service = EventService()
