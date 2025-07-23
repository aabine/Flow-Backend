import httpx
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import settings
from shared.models import EventType, OrderStatus, CylinderSize


class EventService:
    def __init__(self, websocket_manager):
        self.websocket_manager = websocket_manager
        self.websocket_service_url = "http://localhost:8012"
    
    async def emit_inventory_updated(self, vendor_id: str, inventory_id: str, cylinder_size: CylinderSize, 
                                   available_quantity: int, location: dict):
        """Emit inventory update event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/inventory-update",
                    json={
                        "vendor_id": vendor_id,
                        "inventory_id": inventory_id,
                        "cylinder_size": cylinder_size,
                        "available_quantity": available_quantity,
                        "location": location
                    }
                )
        except Exception as e:
            print(f"Failed to emit inventory update: {e}")
    
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
                        "tracking_info": tracking_info
                    }
                )
        except Exception as e:
            print(f"Failed to emit order status change: {e}")
    
    async def emit_emergency_alert(self, title: str, message: str, location: dict, 
                                 radius_km: float = 50.0, severity: str = "high"):
        """Emit emergency alert via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/emergency-alert",
                    json={
                        "title": title,
                        "message": message,
                        "location": location,
                        "radius_km": radius_km,
                        "severity": severity
                    }
                )
        except Exception as e:
            print(f"Failed to emit emergency alert: {e}")
    
    async def emit_delivery_update(self, order_id: str, hospital_id: str, vendor_id: str,
                                 delivery_status: str, current_location: Optional[dict] = None,
                                 eta_minutes: Optional[int] = None):
        """Emit delivery update event via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/broadcast/delivery-update",
                    json={
                        "order_id": order_id,
                        "hospital_id": hospital_id,
                        "vendor_id": vendor_id,
                        "delivery_status": delivery_status,
                        "current_location": current_location,
                        "eta_minutes": eta_minutes
                    }
                )
        except Exception as e:
            print(f"Failed to emit delivery update: {e}")
    
    async def emit_payment_completed(self, payment_id: str, order_id: str, hospital_id: str, 
                                   vendor_id: str, amount: float):
        """Emit payment completed event via WebSocket."""
        try:
            # This would typically send to both hospital and vendor
            message = {
                "type": "payment_completed",
                "payment_id": payment_id,
                "order_id": order_id,
                "amount": amount,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to hospital
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{hospital_id}",
                    json=message
                )
                
                # Send to vendor
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{vendor_id}",
                    json=message
                )
        except Exception as e:
            print(f"Failed to emit payment completed: {e}")
    
    async def emit_low_stock_alert(self, vendor_id: str, inventory_id: str, cylinder_size: CylinderSize,
                                 current_quantity: int, threshold: int):
        """Emit low stock alert to vendor."""
        try:
            message = {
                "type": "low_stock_alert",
                "inventory_id": inventory_id,
                "cylinder_size": cylinder_size,
                "current_quantity": current_quantity,
                "threshold": threshold,
                "severity": "warning" if current_quantity > 0 else "critical",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{vendor_id}",
                    json=message
                )
        except Exception as e:
            print(f"Failed to emit low stock alert: {e}")
    
    async def emit_new_order_notification(self, vendor_id: str, order_id: str, hospital_name: str,
                                        cylinder_size: CylinderSize, quantity: int, is_emergency: bool):
        """Emit new order notification to vendor."""
        try:
            message = {
                "type": "new_order",
                "order_id": order_id,
                "hospital_name": hospital_name,
                "cylinder_size": cylinder_size,
                "quantity": quantity,
                "is_emergency": is_emergency,
                "priority": "high" if is_emergency else "normal",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{vendor_id}",
                    json=message
                )
        except Exception as e:
            print(f"Failed to emit new order notification: {e}")
    
    async def emit_vendor_response_notification(self, hospital_id: str, vendor_name: str, 
                                              order_id: str, response_type: str, eta_minutes: Optional[int] = None):
        """Emit vendor response notification to hospital."""
        try:
            message = {
                "type": "vendor_response",
                "vendor_name": vendor_name,
                "order_id": order_id,
                "response_type": response_type,  # "accepted", "rejected", "counter_offer"
                "eta_minutes": eta_minutes,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{hospital_id}",
                    json=message
                )
        except Exception as e:
            print(f"Failed to emit vendor response notification: {e}")
    
    async def emit_system_maintenance_alert(self, message: str, affected_services: list, 
                                          estimated_duration: Optional[int] = None):
        """Emit system maintenance alert to all users."""
        try:
            alert_message = {
                "type": "system_maintenance",
                "message": message,
                "affected_services": affected_services,
                "estimated_duration_minutes": estimated_duration,
                "severity": "info",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # This would broadcast to all connected users
            # Implementation would depend on WebSocket manager's broadcast functionality
            print(f"System maintenance alert: {message}")
            
        except Exception as e:
            print(f"Failed to emit system maintenance alert: {e}")
    
    async def emit_user_activity_alert(self, admin_id: str, activity_type: str, user_id: str, 
                                     details: dict):
        """Emit user activity alert to admins."""
        try:
            message = {
                "type": "user_activity",
                "activity_type": activity_type,
                "user_id": user_id,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.websocket_service_url}/test-connection/{admin_id}",
                    json=message
                )
        except Exception as e:
            print(f"Failed to emit user activity alert: {e}")
