from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
import uuid
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.order import Order, OrderItem, OrderStatusHistory
from app.schemas.order import OrderCreate, OrderUpdate
from app.core.config import get_settings
from shared.models import OrderStatus, UserRole
from shared.utils import generate_order_reference, calculate_distance_km, calculate_delivery_eta


class OrderService:
    async def create_order(self, db: AsyncSession, hospital_id: str, order_data: OrderCreate) -> Order:
        """Create a new order."""
        # Generate order reference
        reference = generate_order_reference()
        
        # Calculate totals
        subtotal = 0.0
        delivery_fee = 0.0
        emergency_surcharge = 0.0
        
        # Create order
        db_order = Order(
            reference=reference,
            hospital_id=uuid.UUID(hospital_id),
            delivery_address=order_data.delivery_address,
            delivery_latitude=order_data.delivery_latitude,
            delivery_longitude=order_data.delivery_longitude,
            delivery_contact_name=order_data.delivery_contact_name,
            delivery_contact_phone=order_data.delivery_contact_phone,
            is_emergency=order_data.is_emergency,
            notes=order_data.notes,
            special_instructions=order_data.special_instructions,
            requested_delivery_time=order_data.requested_delivery_time,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            emergency_surcharge=emergency_surcharge,
            total_amount=subtotal + delivery_fee + emergency_surcharge
        )
        
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)
        
        # Create order items
        for item_data in order_data.items:
            order_item = OrderItem(
                order_id=db_order.id,
                cylinder_size=item_data.cylinder_size,
                quantity=item_data.quantity
            )
            db.add(order_item)
        
        # Create initial status history
        status_history = OrderStatusHistory(
            order_id=db_order.id,
            status=OrderStatus.PENDING,
            notes="Order created",
            updated_by=uuid.UUID(hospital_id)
        )
        db.add(status_history)
        
        await db.commit()
        
        # If preferred vendor specified, try to assign
        if order_data.preferred_vendor_id:
            await self._try_assign_vendor(db, db_order.id, order_data.preferred_vendor_id)
        
        return db_order
    
    async def get_order_by_id(self, db: AsyncSession, order_id: str) -> Optional[Order]:
        """Get order by ID with all related data."""
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.status_history))
            .filter(Order.id == uuid.UUID(order_id))
        )
        return result.scalar_one_or_none()
    
    async def get_user_orders(
        self, 
        db: AsyncSession, 
        user_id: str, 
        user_role: str, 
        page: int = 1, 
        size: int = 20,
        status_filter: Optional[OrderStatus] = None
    ) -> Tuple[List[Order], int]:
        """Get orders for a user based on their role."""
        query = select(Order).options(selectinload(Order.items))
        
        # Filter by user role
        if user_role == UserRole.HOSPITAL:
            query = query.filter(Order.hospital_id == uuid.UUID(user_id))
        elif user_role == UserRole.VENDOR:
            query = query.filter(Order.vendor_id == uuid.UUID(user_id))
        # Admin can see all orders
        
        # Apply status filter
        if status_filter:
            query = query.filter(Order.status == status_filter)
        
        # Get total count
        count_query = select(Order.id)
        if user_role == UserRole.HOSPITAL:
            count_query = count_query.filter(Order.hospital_id == uuid.UUID(user_id))
        elif user_role == UserRole.VENDOR:
            count_query = count_query.filter(Order.vendor_id == uuid.UUID(user_id))
        if status_filter:
            count_query = count_query.filter(Order.status == status_filter)
        
        total_result = await db.execute(count_query)
        total = len(total_result.all())
        
        # Apply pagination
        query = query.order_by(Order.created_at.desc())
        query = query.offset((page - 1) * size).limit(size)
        
        result = await db.execute(query)
        orders = result.scalars().all()
        
        return list(orders), total
    
    async def update_order(self, db: AsyncSession, order_id: str, order_update: OrderUpdate) -> Order:
        """Update order."""
        update_data = order_update.dict(exclude_unset=True)
        
        if update_data:
            stmt = update(Order).where(Order.id == uuid.UUID(order_id)).values(**update_data)
            await db.execute(stmt)
            await db.commit()
        
        return await self.get_order_by_id(db, order_id)
    
    async def accept_order(self, db: AsyncSession, order_id: str, vendor_id: str) -> Order:
        """Accept order by vendor."""
        # Update order with vendor and status
        stmt = update(Order).where(
            and_(
                Order.id == uuid.UUID(order_id),
                Order.status == OrderStatus.PENDING
            )
        ).values(
            vendor_id=uuid.UUID(vendor_id),
            status=OrderStatus.CONFIRMED
        )
        
        result = await db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Order not found or cannot be accepted")
        
        # Add status history
        status_history = OrderStatusHistory(
            order_id=uuid.UUID(order_id),
            status=OrderStatus.CONFIRMED,
            notes="Order accepted by vendor",
            updated_by=uuid.UUID(vendor_id)
        )
        db.add(status_history)
        
        await db.commit()
        
        return await self.get_order_by_id(db, order_id)
    
    async def cancel_order(self, db: AsyncSession, order_id: str, reason: Optional[str] = None) -> Order:
        """Cancel order."""
        stmt = update(Order).where(
            and_(
                Order.id == uuid.UUID(order_id),
                Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED])
            )
        ).values(
            status=OrderStatus.CANCELLED,
            cancellation_reason=reason
        )
        
        result = await db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Order not found or cannot be cancelled")
        
        await db.commit()
        
        return await self.get_order_by_id(db, order_id)
    
    async def can_access_order(self, order: Order, user_id: str, user_role: str) -> bool:
        """Check if user can access order."""
        if user_role == UserRole.ADMIN:
            return True
        elif user_role == UserRole.HOSPITAL:
            return str(order.hospital_id) == user_id
        elif user_role == UserRole.VENDOR:
            return str(order.vendor_id) == user_id if order.vendor_id else False
        
        return False
    
    async def can_update_order(self, order: Order, user_id: str, user_role: str, update_data: OrderUpdate) -> bool:
        """Check if user can update order."""
        if user_role == UserRole.ADMIN:
            return True
        
        # Hospitals can only update notes and cancel
        if user_role == UserRole.HOSPITAL and str(order.hospital_id) == user_id:
            allowed_fields = {'notes', 'special_instructions'}
            update_fields = set(update_data.dict(exclude_unset=True).keys())
            return update_fields.issubset(allowed_fields)
        
        # Vendors can update status and delivery info
        if user_role == UserRole.VENDOR and str(order.vendor_id) == user_id:
            allowed_fields = {'status', 'delivery_notes', 'estimated_delivery_time', 
                            'actual_delivery_time', 'tracking_number'}
            update_fields = set(update_data.dict(exclude_unset=True).keys())
            return update_fields.issubset(allowed_fields)
        
        return False
    
    async def can_cancel_order(self, order: Order, user_id: str, user_role: str) -> bool:
        """Check if user can cancel order."""
        if user_role == UserRole.ADMIN:
            return True
        
        # Only pending or confirmed orders can be cancelled
        if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
            return False
        
        # Hospital can cancel their own orders
        if user_role == UserRole.HOSPITAL and str(order.hospital_id) == user_id:
            return True
        
        # Vendor can cancel confirmed orders
        if user_role == UserRole.VENDOR and str(order.vendor_id) == user_id:
            return order.status == OrderStatus.CONFIRMED
        
        return False
    
    async def get_emergency_orders(self, db: AsyncSession, user_id: str, user_role: str) -> List[Order]:
        """Get emergency orders."""
        query = select(Order).options(selectinload(Order.items)).filter(
            and_(
                Order.is_emergency == True,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED])
            )
        )
        
        # Vendors only see unassigned emergency orders or their own
        if user_role == UserRole.VENDOR:
            query = query.filter(
                or_(
                    Order.vendor_id.is_(None),
                    Order.vendor_id == uuid.UUID(user_id)
                )
            )
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_order_tracking(self, db: AsyncSession, order_id: str) -> dict:
        """Get order tracking information."""
        order = await self.get_order_by_id(db, order_id)
        if not order:
            return {}
        
        # Calculate ETA if order is in transit
        eta_minutes = None
        if order.status == OrderStatus.IN_TRANSIT and order.estimated_delivery_time:
            time_diff = order.estimated_delivery_time - datetime.utcnow()
            eta_minutes = max(0, int(time_diff.total_seconds() / 60))
        
        return {
            "status": order.status,
            "tracking_number": order.tracking_number,
            "estimated_delivery": order.estimated_delivery_time,
            "eta_minutes": eta_minutes,
            "delivery_notes": order.delivery_notes,
            "status_history": [
                {
                    "status": history.status,
                    "timestamp": history.created_at,
                    "notes": history.notes
                }
                for history in order.status_history
            ]
        }
    
    async def _try_assign_vendor(self, db: AsyncSession, order_id: uuid.UUID, vendor_id: str) -> bool:
        """Try to assign vendor to order."""
        try:
            # Check if vendor is available (call inventory service)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{get_settings().INVENTORY_SERVICE_URL}/vendors/{vendor_id}/availability"
                )
                if response.status_code == 200:
                    stmt = update(Order).where(Order.id == order_id).values(vendor_id=uuid.UUID(vendor_id))
                    await db.execute(stmt)
                    await db.commit()
                    return True
        except Exception:
            pass
        
        return False
