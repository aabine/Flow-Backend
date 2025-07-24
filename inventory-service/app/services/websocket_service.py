import json
import asyncio
from typing import Dict, List, Set, Any
from datetime import datetime
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings

settings = get_settings()


class InventoryWebSocketService:
    def __init__(self):
        self.settings = settings
        self.websocket_service_url = self.settings.WEBSOCKET_SERVICE_URL
        
    async def broadcast_stock_update(self, inventory_data: Dict[str, Any]):
        """Broadcast stock level updates to connected clients."""
        try:
            message = {
                "type": "stock_update",
                "data": {
                    "inventory_id": inventory_data.get("inventory_id"),
                    "vendor_id": inventory_data.get("vendor_id"),
                    "location_id": inventory_data.get("location_id"),
                    "cylinder_size": inventory_data.get("cylinder_size"),
                    "available_quantity": inventory_data.get("available_quantity"),
                    "reserved_quantity": inventory_data.get("reserved_quantity"),
                    "total_quantity": inventory_data.get("total_quantity"),
                    "low_stock_threshold": inventory_data.get("low_stock_threshold"),
                    "is_low_stock": inventory_data.get("is_low_stock", False),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self._send_websocket_message("inventory_updates", message)
            
        except Exception as e:
            print(f"Error broadcasting stock update: {e}")

    async def broadcast_low_stock_alert(self, inventory_data: Dict[str, Any]):
        """Broadcast low stock alerts to relevant users."""
        try:
            message = {
                "type": "low_stock_alert",
                "data": {
                    "inventory_id": inventory_data.get("inventory_id"),
                    "vendor_id": inventory_data.get("vendor_id"),
                    "location_name": inventory_data.get("location_name"),
                    "cylinder_size": inventory_data.get("cylinder_size"),
                    "current_quantity": inventory_data.get("available_quantity"),
                    "threshold": inventory_data.get("low_stock_threshold"),
                    "severity": self._calculate_alert_severity(
                        inventory_data.get("available_quantity", 0),
                        inventory_data.get("low_stock_threshold", 0)
                    ),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to vendor-specific channel
            vendor_channel = f"vendor_{inventory_data.get('vendor_id')}"
            await self._send_websocket_message(vendor_channel, message)
            
            # Send to admin channel for monitoring
            await self._send_websocket_message("admin_alerts", message)
            
        except Exception as e:
            print(f"Error broadcasting low stock alert: {e}")

    async def broadcast_reservation_update(self, reservation_data: Dict[str, Any]):
        """Broadcast inventory reservation updates."""
        try:
            message = {
                "type": "reservation_update",
                "data": {
                    "reservation_id": reservation_data.get("reservation_id"),
                    "inventory_id": reservation_data.get("inventory_id"),
                    "order_id": reservation_data.get("order_id"),
                    "quantity": reservation_data.get("quantity"),
                    "status": reservation_data.get("status"),
                    "expires_at": reservation_data.get("expires_at"),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to order-specific channel
            order_channel = f"order_{reservation_data.get('order_id')}"
            await self._send_websocket_message(order_channel, message)
            
            # Send to vendor channel
            vendor_channel = f"vendor_{reservation_data.get('vendor_id')}"
            await self._send_websocket_message(vendor_channel, message)
            
        except Exception as e:
            print(f"Error broadcasting reservation update: {e}")

    async def broadcast_stock_movement(self, movement_data: Dict[str, Any]):
        """Broadcast stock movement events."""
        try:
            message = {
                "type": "stock_movement",
                "data": {
                    "movement_id": movement_data.get("movement_id"),
                    "inventory_id": movement_data.get("inventory_id"),
                    "movement_type": movement_data.get("movement_type"),
                    "quantity": movement_data.get("quantity"),
                    "reference_id": movement_data.get("reference_id"),
                    "notes": movement_data.get("notes"),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to vendor channel
            vendor_channel = f"vendor_{movement_data.get('vendor_id')}"
            await self._send_websocket_message(vendor_channel, message)
            
            # Send to admin channel for monitoring
            await self._send_websocket_message("admin_monitoring", message)
            
        except Exception as e:
            print(f"Error broadcasting stock movement: {e}")

    async def broadcast_inventory_location_update(self, location_data: Dict[str, Any]):
        """Broadcast inventory location updates."""
        try:
            message = {
                "type": "location_update",
                "data": {
                    "location_id": location_data.get("location_id"),
                    "vendor_id": location_data.get("vendor_id"),
                    "location_name": location_data.get("location_name"),
                    "is_active": location_data.get("is_active"),
                    "total_inventory_items": location_data.get("total_inventory_items", 0),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to vendor channel
            vendor_channel = f"vendor_{location_data.get('vendor_id')}"
            await self._send_websocket_message(vendor_channel, message)
            
            # Send to location-based updates
            await self._send_websocket_message("location_updates", message)
            
        except Exception as e:
            print(f"Error broadcasting location update: {e}")

    async def notify_order_service_stock_change(self, inventory_data: Dict[str, Any]):
        """Notify order service of stock changes for order processing."""
        try:
            notification = {
                "inventory_id": inventory_data.get("inventory_id"),
                "vendor_id": inventory_data.get("vendor_id"),
                "cylinder_size": inventory_data.get("cylinder_size"),
                "available_quantity": inventory_data.get("available_quantity"),
                "location": {
                    "id": inventory_data.get("location_id"),
                    "name": inventory_data.get("location_name"),
                    "latitude": inventory_data.get("latitude"),
                    "longitude": inventory_data.get("longitude")
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to order service via WebSocket
            await self._send_websocket_message("order_service_notifications", {
                "type": "inventory_availability_update",
                "data": notification,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            print(f"Error notifying order service: {e}")

    async def _send_websocket_message(self, channel: str, message: Dict[str, Any]):
        """Send message to WebSocket service for broadcasting."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.websocket_service_url}/broadcast",
                    json={
                        "channel": channel,
                        "message": message
                    },
                    timeout=5.0
                )
                
                if response.status_code != 200:
                    print(f"WebSocket service returned status {response.status_code}")
                    
        except httpx.TimeoutException:
            print(f"Timeout sending WebSocket message to channel {channel}")
        except Exception as e:
            print(f"Error sending WebSocket message: {e}")

    def _calculate_alert_severity(self, current_quantity: int, threshold: int) -> str:
        """Calculate alert severity based on stock levels."""
        if current_quantity == 0:
            return "critical"
        elif current_quantity <= threshold * 0.5:
            return "high"
        elif current_quantity <= threshold:
            return "medium"
        else:
            return "low"

    async def get_real_time_inventory_summary(self, vendor_id: str = None) -> Dict[str, Any]:
        """Get real-time inventory summary for dashboard."""
        try:
            # This would typically aggregate current inventory data
            # For now, return a placeholder structure
            summary = {
                "total_locations": 0,
                "total_inventory_items": 0,
                "low_stock_items": 0,
                "out_of_stock_items": 0,
                "total_reserved": 0,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            if vendor_id:
                summary["vendor_id"] = vendor_id
            
            return summary
            
        except Exception as e:
            print(f"Error getting inventory summary: {e}")
            return {}

    async def broadcast_bulk_stock_update(self, inventory_updates: List[Dict[str, Any]]):
        """Broadcast multiple stock updates efficiently."""
        try:
            message = {
                "type": "bulk_stock_update",
                "data": {
                    "updates": inventory_updates,
                    "count": len(inventory_updates),
                    "timestamp": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self._send_websocket_message("inventory_updates", message)
            
            # Also send to admin monitoring
            await self._send_websocket_message("admin_monitoring", message)
            
        except Exception as e:
            print(f"Error broadcasting bulk stock update: {e}")


# Global WebSocket service instance
websocket_service = InventoryWebSocketService()
