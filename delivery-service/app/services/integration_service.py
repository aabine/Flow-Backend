import httpx
import logging
from typing import Dict, Any, Optional
import json

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class IntegrationService:
    """Service for integrating with external microservices."""

    def __init__(self):
        self.timeout = httpx.Timeout(30.0)

    async def notify_order_service(self, order_id: str, status: str, delivery_data: Dict[str, Any]) -> bool:
        """Notify order service about delivery status update."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.ORDER_SERVICE_URL}/api/v1/orders/{order_id}/delivery-status",
                    json={
                        "status": status,
                        "delivery_data": delivery_data
                    }
                )
                response.raise_for_status()
                logger.info(f"Notified order service about delivery {order_id} status: {status}")
                return True
        except Exception as e:
            logger.error(f"Failed to notify order service: {e}")
            return False

    async def validate_address(self, address: str, lat: float, lng: float) -> Dict[str, Any]:
        """Validate address using location service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.LOCATION_SERVICE_URL}/api/v1/validate",
                    json={
                        "address": address,
                        "latitude": lat,
                        "longitude": lng
                    }
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Address validation result: {result}")
                return result
        except Exception as e:
            logger.error(f"Failed to validate address: {e}")
            return {"valid": False, "error": str(e)}

    async def geocode_address(self, address: str) -> Optional[Dict[str, float]]:
        """Geocode address using location service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.LOCATION_SERVICE_URL}/api/v1/geocode",
                    json={"address": address}
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success") and result.get("data"):
                    return {
                        "lat": result["data"]["latitude"],
                        "lng": result["data"]["longitude"]
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to geocode address: {e}")
            return None

    async def send_notification(self, notification_type: str, recipient: str, 
                              template: str, data: Dict[str, Any]) -> bool:
        """Send notification via notification service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.NOTIFICATION_SERVICE_URL}/api/v1/notifications/send",
                    json={
                        "type": notification_type,
                        "recipient": recipient,
                        "template": template,
                        "data": data
                    }
                )
                response.raise_for_status()
                logger.info(f"Sent {notification_type} notification to {recipient}")
                return True
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def send_realtime_update(self, channel: str, event: str, data: Dict[str, Any]) -> bool:
        """Send real-time update via WebSocket service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.WEBSOCKET_SERVICE_URL}/api/v1/broadcast",
                    json={
                        "channel": channel,
                        "event": event,
                        "data": data
                    }
                )
                response.raise_for_status()
                logger.info(f"Sent real-time update to channel {channel}")
                return True
        except Exception as e:
            logger.error(f"Failed to send real-time update: {e}")
            return False

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information from user service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{settings.USER_SERVICE_URL}/api/v1/users/{user_id}"
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("success") and result.get("data"):
                    return result["data"]
                return None
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    async def check_inventory_availability(self, cylinder_size: str, quantity: int, 
                                         location_lat: float, location_lng: float) -> Dict[str, Any]:
        """Check inventory availability via inventory service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.INVENTORY_SERVICE_URL}/api/v1/inventory/check-availability",
                    json={
                        "cylinder_size": cylinder_size,
                        "quantity": quantity,
                        "location": {
                            "lat": location_lat,
                            "lng": location_lng
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"Inventory availability check result: {result}")
                return result
        except Exception as e:
            logger.error(f"Failed to check inventory availability: {e}")
            return {"available": False, "error": str(e)}

    async def reserve_inventory(self, inventory_id: str, quantity: int, order_id: str) -> bool:
        """Reserve inventory via inventory service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{settings.INVENTORY_SERVICE_URL}/api/v1/inventory/{inventory_id}/reserve",
                    json={
                        "quantity": quantity,
                        "order_id": order_id
                    }
                )
                response.raise_for_status()
                logger.info(f"Reserved inventory {inventory_id} for order {order_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to reserve inventory: {e}")
            return False

    async def release_inventory_reservation(self, inventory_id: str, order_id: str) -> bool:
        """Release inventory reservation via inventory service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.delete(
                    f"{settings.INVENTORY_SERVICE_URL}/api/v1/inventory/{inventory_id}/reserve/{order_id}"
                )
                response.raise_for_status()
                logger.info(f"Released inventory reservation for order {order_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to release inventory reservation: {e}")
            return False


# Notification templates and helper functions
class NotificationTemplates:
    """Predefined notification templates for delivery events."""
    
    DELIVERY_ASSIGNED = "delivery_assigned"
    DELIVERY_PICKED_UP = "delivery_picked_up"
    DELIVERY_IN_TRANSIT = "delivery_in_transit"
    DELIVERY_OUT_FOR_DELIVERY = "delivery_out_for_delivery"
    DELIVERY_DELIVERED = "delivery_delivered"
    DELIVERY_FAILED = "delivery_failed"
    DELIVERY_CANCELLED = "delivery_cancelled"
    
    DRIVER_ASSIGNMENT = "driver_assignment"
    DRIVER_ROUTE_UPDATED = "driver_route_updated"


async def send_delivery_status_notification(delivery_id: str, status: str, 
                                          customer_id: str, driver_id: str = None):
    """Send delivery status notification to customer and driver."""
    integration_service = IntegrationService()
    
    # Notification data
    notification_data = {
        "delivery_id": delivery_id,
        "status": status,
        "timestamp": json.dumps({"$date": {"$numberLong": str(int(logger.time() * 1000))}})
    }
    
    # Send to customer
    await integration_service.send_notification(
        "push", customer_id, f"delivery_{status.lower()}", notification_data
    )
    
    # Send to driver if assigned
    if driver_id:
        await integration_service.send_notification(
            "push", driver_id, f"driver_delivery_{status.lower()}", notification_data
        )
    
    # Send real-time update
    await integration_service.send_realtime_update(
        f"delivery_{delivery_id}", "status_update", notification_data
    )
