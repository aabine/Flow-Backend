import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import EventType


class EventService:
    """Service for handling events and notifications."""
    
    def __init__(self):
        self.event_queue = asyncio.Queue()
    
    async def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source_service: str = "inventory-service"
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
            
            # In a real implementation, this would publish to RabbitMQ, Redis, or similar
            # For now, we'll just add to a local queue
            await self.event_queue.put(event)
            
            print(f"Event published: {event_type.value} from {source_service}")
            return True
            
        except Exception as e:
            print(f"Failed to publish event: {str(e)}")
            return False
    
    async def publish_inventory_updated(
        self,
        inventory_id: str,
        vendor_id: str,
        cylinder_size: str,
        quantity_change: int,
        new_quantity: int
    ):
        """Publish inventory updated event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "cylinder_size": cylinder_size,
                "quantity_change": quantity_change,
                "new_quantity": new_quantity
            }
        )
    
    async def publish_low_stock_alert(
        self,
        inventory_id: str,
        vendor_id: str,
        cylinder_size: str,
        current_quantity: int,
        minimum_threshold: int
    ):
        """Publish low stock alert event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,  # Using existing event type
            {
                "alert_type": "low_stock",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "cylinder_size": cylinder_size,
                "current_quantity": current_quantity,
                "minimum_threshold": minimum_threshold
            }
        )
    
    async def publish_stock_reserved(
        self,
        inventory_id: str,
        vendor_id: str,
        order_id: str,
        cylinder_size: str,
        quantity: int
    ):
        """Publish stock reserved event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "action": "stock_reserved",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "order_id": order_id,
                "cylinder_size": cylinder_size,
                "quantity": quantity
            }
        )
    
    async def publish_stock_released(
        self,
        inventory_id: str,
        vendor_id: str,
        order_id: str,
        cylinder_size: str,
        quantity: int
    ):
        """Publish stock released event."""
        await self.publish_event(
            EventType.INVENTORY_UPDATED,
            {
                "action": "stock_released",
                "inventory_id": inventory_id,
                "vendor_id": vendor_id,
                "order_id": order_id,
                "cylinder_size": cylinder_size,
                "quantity": quantity
            }
        )
    
    async def process_events(self):
        """Process events from the queue (background task)."""
        while True:
            try:
                event = await self.event_queue.get()
                # In a real implementation, this would send to message broker
                print(f"Processing event: {json.dumps(event, indent=2)}")
                self.event_queue.task_done()
            except Exception as e:
                print(f"Error processing event: {str(e)}")
                await asyncio.sleep(1)
