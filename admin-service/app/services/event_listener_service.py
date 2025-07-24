import json
import asyncio
import aio_pika
from typing import Dict, Any, Callable
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.admin import SystemMetrics, SystemAlert, MetricType
from app.services.system_monitoring_service import SystemMonitoringService

settings = get_settings()


class EventListenerService:
    def __init__(self):
        self.settings = settings
        self.connection = None
        self.channel = None
        self.monitoring_service = SystemMonitoringService()
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

    async def start_listening(self):
        """Start listening to events from all services."""
        try:
            # Connect to RabbitMQ
            self.connection = await aio_pika.connect_robust(self.settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()
            
            # Set up exchanges and queues
            await self._setup_event_infrastructure()
            
            print("Event listener service started successfully")
            
        except Exception as e:
            print(f"Failed to start event listener service: {e}")
            raise

    async def stop_listening(self):
        """Stop listening to events and close connections."""
        if self.connection:
            await self.connection.close()
            print("Event listener service stopped")

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

    async def _process_event(self, message: aio_pika.IncomingMessage):
        """Process incoming events."""
        async with message.process():
            try:
                # Parse event data
                event_data = json.loads(message.body.decode())
                routing_key = message.routing_key
                
                print(f"Processing event: {routing_key}")
                
                # Handle the event
                handler = self.event_handlers.get(routing_key)
                if handler:
                    await handler(event_data)
                else:
                    print(f"No handler found for event: {routing_key}")
                
            except Exception as e:
                print(f"Error processing event {message.routing_key}: {e}")

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
