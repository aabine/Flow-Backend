import httpx
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import EventType, OrderStatus


class EventService:
    """Service for handling order-related events and notifications."""
    
    def __init__(self):
        self.websocket_service_url = "http://websocket-service:8012"
        self.event_queue = asyncio.Queue()
    
    async def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_service: str = "order-service"
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
            
            # Add to local queue for processing
            await self.event_queue.put(event)
            
            print(f"Event published: {event_type.value} from {source_service}")
            return True
            
        except Exception as e:
            print(f"Failed to publish event: {str(e)}")
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
