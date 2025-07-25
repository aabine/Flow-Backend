import json
import asyncio
import aio_pika
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import sys
import os
import logging
from enum import Enum

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.admin import SystemMetrics, SystemAlert, MetricType
from app.services.system_monitoring_service import SystemMonitoringService

settings = get_settings()
logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """RabbitMQ connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class EventListenerService:
    """
    Resilient service for listening to events from other microservices.
    Handles RabbitMQ connection failures gracefully and provides fallback mechanisms.
    """

    def __init__(self):
        self.settings = settings
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        self.monitoring_service = SystemMonitoringService()
        self.connection_state = ConnectionState.DISCONNECTED
        self.reconnect_task: Optional[asyncio.Task] = None
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.is_running = False

        # Event handlers mapping
        self.event_handlers = {
            "order.created": self._handle_order_created,
            "order.completed": self._handle_order_completed,
            "order.cancelled": self._handle_order_cancelled,
            "payment.completed": self._handle_payment_completed,
            "payment.failed": self._handle_payment_failed,
            "review.created": self._handle_review_created,
            "user.registered": self._handle_user_registered,
            "user.suspended": self._handle_user_suspended,
            "system.error": self._handle_system_error,
            "service.health_check": self._handle_service_health_check,
        }

        # Fallback event storage for when RabbitMQ is unavailable
        self.pending_events = []
        self.max_pending_events = 1000

    async def start_listening(self):
        """
        Start listening to events from all services with graceful error handling.
        Service will start even if RabbitMQ is unavailable.
        """
        self.is_running = True
        logger.info("Starting Event Listener Service...")

        # Start connection attempt in background
        self.reconnect_task = asyncio.create_task(self._connect_with_retry())

        logger.info("Event Listener Service started (will connect to RabbitMQ when available)")
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

    async def stop_listening(self):
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
        logger.info("Event listener service stopped")

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
                await self._process_event(event_data)
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

    async def publish_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        Publish an event. If RabbitMQ is unavailable, store locally.
        """
        if self.connection_state == ConnectionState.CONNECTED and self.channel:
            try:
                # Try to publish to RabbitMQ
                message = aio_pika.Message(
                    json.dumps(event_data).encode(),
                    content_type="application/json"
                )

                await self.channel.default_exchange.publish(
                    message,
                    routing_key=event_type
                )
                logger.debug(f"Published event {event_type} to RabbitMQ")
                return

            except Exception as e:
                logger.warning(f"Failed to publish event to RabbitMQ: {e}")

        # Fallback: store event locally
        if len(self.pending_events) < self.max_pending_events:
            self.pending_events.append({
                "type": event_type,
                "data": event_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.debug(f"Stored event {event_type} locally (RabbitMQ unavailable)")
        else:
            logger.warning(f"Pending events buffer full, dropping event {event_type}")

    async def _setup_event_infrastructure(self):
        """Set up RabbitMQ exchanges and queues for event listening."""
        
        # Declare exchanges for different services
        exchanges = [
            "order_events",
            "payment_events", 
            "review_events",
            "user_events",
            "system_events"
        ]
        
        for exchange_name in exchanges:
            exchange = await self.channel.declare_exchange(
                exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
        
        # Create admin service queue
        admin_queue = await self.channel.declare_queue(
            "admin_service_events",
            durable=True
        )
        
        # Bind queue to all exchanges with relevant routing keys
        routing_patterns = [
            ("order_events", "order.*"),
            ("payment_events", "payment.*"),
            ("review_events", "review.*"),
            ("user_events", "user.*"),
            ("system_events", "system.*"),
        ]
        
        for exchange_name, pattern in routing_patterns:
            exchange = await self.channel.get_exchange(exchange_name)
            await admin_queue.bind(exchange, routing_key=pattern)
        
        # Start consuming messages
        await admin_queue.consume(self._process_event)

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
                routing_key = message_or_data.get("type", "unknown")

            logger.debug(f"Processing event: {routing_key}")

            # Handle the event
            handler = self.event_handlers.get(routing_key)
            if handler:
                await handler(event_data)
                logger.debug(f"Successfully processed event: {routing_key}")
            else:
                logger.warning(f"No handler found for event: {routing_key}")

        except Exception as e:
            logger.error(f"Error processing event {routing_key if 'routing_key' in locals() else 'unknown'}: {e}")
            # Don't re-raise to prevent message requeue loops

    # Event Handlers
    async def _handle_order_created(self, event_data: Dict[str, Any]):
        """Handle order creation events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update order count metric
                await self._store_metric(
                    db, MetricType.ORDER_COUNT, "order-service", 1, "count",
                    {"event": "order_created", "order_id": event_data.get("order_id")}
                )
                
                # Check for emergency orders and create alerts if needed
                if event_data.get("is_emergency"):
                    await self.monitoring_service.create_alert(
                        db,
                        alert_type="info",
                        severity="medium",
                        title="Emergency Order Created",
                        message=f"Emergency order {event_data.get('order_id')} created",
                        service_name="order-service",
                        details=event_data
                    )
                
            except Exception as e:
                print(f"Error handling order created event: {e}")

    async def _handle_order_completed(self, event_data: Dict[str, Any]):
        """Handle order completion events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update completion metrics
                await self._store_metric(
                    db, MetricType.ORDER_COUNT, "order-service", 1, "count",
                    {"event": "order_completed", "order_id": event_data.get("order_id")}
                )
                
            except Exception as e:
                print(f"Error handling order completed event: {e}")

    async def _handle_order_cancelled(self, event_data: Dict[str, Any]):
        """Handle order cancellation events."""
        async with AsyncSessionLocal() as db:
            try:
                # Track cancellation rate
                await self._store_metric(
                    db, MetricType.ORDER_COUNT, "order-service", 1, "count",
                    {"event": "order_cancelled", "order_id": event_data.get("order_id")}
                )
                
                # Create alert for high cancellation rates (would need additional logic)
                
            except Exception as e:
                print(f"Error handling order cancelled event: {e}")

    async def _handle_payment_completed(self, event_data: Dict[str, Any]):
        """Handle payment completion events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update revenue metrics
                amount = event_data.get("amount", 0)
                await self._store_metric(
                    db, MetricType.REVENUE, "payment-service", amount, "NGN",
                    {"event": "payment_completed", "payment_id": event_data.get("payment_id")}
                )
                
            except Exception as e:
                print(f"Error handling payment completed event: {e}")

    async def _handle_payment_failed(self, event_data: Dict[str, Any]):
        """Handle payment failure events."""
        async with AsyncSessionLocal() as db:
            try:
                # Track payment failures
                await self._store_metric(
                    db, MetricType.ERROR_RATE, "payment-service", 1, "count",
                    {"event": "payment_failed", "payment_id": event_data.get("payment_id")}
                )
                
                # Create alert for payment failures
                await self.monitoring_service.create_alert(
                    db,
                    alert_type="warning",
                    severity="medium",
                    title="Payment Failed",
                    message=f"Payment {event_data.get('payment_id')} failed: {event_data.get('reason', 'Unknown')}",
                    service_name="payment-service",
                    details=event_data
                )
                
            except Exception as e:
                print(f"Error handling payment failed event: {e}")

    async def _handle_review_created(self, event_data: Dict[str, Any]):
        """Handle review creation events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update review count metrics
                await self._store_metric(
                    db, MetricType.REVIEW_COUNT, "review-service", 1, "count",
                    {"event": "review_created", "review_id": event_data.get("review_id")}
                )
                
            except Exception as e:
                print(f"Error handling review created event: {e}")

    async def _handle_user_registered(self, event_data: Dict[str, Any]):
        """Handle user registration events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update user count metrics
                await self._store_metric(
                    db, MetricType.USER_COUNT, "user-service", 1, "count",
                    {"event": "user_registered", "user_id": event_data.get("user_id")}
                )
                
            except Exception as e:
                print(f"Error handling user registered event: {e}")

    async def _handle_user_suspended(self, event_data: Dict[str, Any]):
        """Handle user suspension events."""
        async with AsyncSessionLocal() as db:
            try:
                # Create alert for user suspension
                await self.monitoring_service.create_alert(
                    db,
                    alert_type="info",
                    severity="low",
                    title="User Suspended",
                    message=f"User {event_data.get('user_id')} suspended: {event_data.get('reason', 'No reason provided')}",
                    service_name="user-service",
                    details=event_data
                )
                
            except Exception as e:
                print(f"Error handling user suspended event: {e}")

    async def _handle_system_error(self, event_data: Dict[str, Any]):
        """Handle system error events."""
        async with AsyncSessionLocal() as db:
            try:
                # Create critical alert for system errors
                severity = "critical" if event_data.get("error_level") == "critical" else "high"
                
                await self.monitoring_service.create_alert(
                    db,
                    alert_type="error",
                    severity=severity,
                    title=f"System Error in {event_data.get('service_name', 'Unknown Service')}",
                    message=event_data.get("error_message", "System error occurred"),
                    service_name=event_data.get("service_name", "unknown"),
                    details=event_data
                )
                
            except Exception as e:
                print(f"Error handling system error event: {e}")

    async def _handle_service_health_check(self, event_data: Dict[str, Any]):
        """Handle service health check events."""
        async with AsyncSessionLocal() as db:
            try:
                # Update service health metrics
                service_name = event_data.get("service_name")
                status = event_data.get("status")
                response_time = event_data.get("response_time", 0)
                
                if response_time:
                    await self._store_metric(
                        db, MetricType.RESPONSE_TIME, service_name, response_time, "milliseconds",
                        {"event": "health_check", "status": status}
                    )
                
                # Create alert if service is down
                if status == "down":
                    await self.monitoring_service.create_alert(
                        db,
                        alert_type="error",
                        severity="high",
                        title=f"Service Down: {service_name}",
                        message=f"Health check failed for {service_name}",
                        service_name=service_name,
                        details=event_data
                    )
                
            except Exception as e:
                print(f"Error handling service health check event: {e}")

    async def _store_metric(
        self,
        db: AsyncSession,
        metric_type: MetricType,
        service_name: str,
        value: float,
        unit: str,
        metadata: Dict[str, Any] = None
    ):
        """Store a metric in the database."""
        try:
            metric = SystemMetrics(
                metric_type=metric_type,
                service_name=service_name,
                value=value,
                unit=unit,
                metadata=metadata
            )
            
            db.add(metric)
            await db.commit()
            
        except Exception as e:
            print(f"Error storing metric: {e}")
            await db.rollback()


# Global event listener instance
event_listener = EventListenerService()
