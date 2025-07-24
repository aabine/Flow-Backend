from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import logging

from app.models.delivery import Delivery, Driver, DeliveryTracking, DeliveryStatus, DriverStatus
from app.schemas.delivery import (
    DeliveryCreate, DeliveryUpdate, DeliveryFilters, 
    TrackingUpdate, DeliveryAssignment
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DeliveryService:
    """Service for managing deliveries."""

    async def create_delivery(self, db: AsyncSession, delivery_data: DeliveryCreate) -> Delivery:
        """Create a new delivery."""
        try:
            # Calculate distance and ETA
            distance_km = await self._calculate_distance(
                delivery_data.pickup_lat, delivery_data.pickup_lng,
                delivery_data.delivery_lat, delivery_data.delivery_lng
            )
            
            delivery = Delivery(
                order_id=delivery_data.order_id,
                customer_id=delivery_data.customer_id,
                cylinder_size=delivery_data.cylinder_size,
                quantity=delivery_data.quantity,
                priority=delivery_data.priority,
                pickup_address=delivery_data.pickup_address,
                pickup_lat=delivery_data.pickup_lat,
                pickup_lng=delivery_data.pickup_lng,
                delivery_address=delivery_data.delivery_address,
                delivery_lat=delivery_data.delivery_lat,
                delivery_lng=delivery_data.delivery_lng,
                requested_delivery_time=delivery_data.requested_delivery_time,
                delivery_fee=delivery_data.delivery_fee,
                special_instructions=delivery_data.special_instructions,
                distance_km=distance_km
            )
            
            db.add(delivery)
            await db.commit()
            await db.refresh(delivery)
            
            # Create initial tracking entry
            await self.add_tracking_update(
                db, str(delivery.id), 
                TrackingUpdate(status=DeliveryStatus.PENDING),
                "system"
            )
            
            logger.info(f"Created delivery {delivery.id} for order {delivery.order_id}")
            return delivery
            
        except Exception as e:
            logger.error(f"Error creating delivery: {e}")
            await db.rollback()
            raise

    async def get_delivery(self, db: AsyncSession, delivery_id: str) -> Optional[Delivery]:
        """Get delivery by ID."""
        try:
            result = await db.execute(
                select(Delivery)
                .options(selectinload(Delivery.driver), selectinload(Delivery.tracking_updates))
                .where(Delivery.id == uuid.UUID(delivery_id))
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting delivery {delivery_id}: {e}")
            return None

    async def update_delivery(self, db: AsyncSession, delivery_id: str, 
                            delivery_data: DeliveryUpdate) -> Optional[Delivery]:
        """Update delivery."""
        try:
            delivery = await self.get_delivery(db, delivery_id)
            if not delivery:
                return None
            
            update_data = delivery_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(delivery, field, value)
            
            delivery.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(delivery)
            
            # Add tracking update if status changed
            if delivery_data.status:
                await self.add_tracking_update(
                    db, delivery_id,
                    TrackingUpdate(status=delivery_data.status),
                    "system"
                )
            
            logger.info(f"Updated delivery {delivery_id}")
            return delivery
            
        except Exception as e:
            logger.error(f"Error updating delivery {delivery_id}: {e}")
            await db.rollback()
            raise

    async def get_deliveries(self, db: AsyncSession, filters: DeliveryFilters, 
                           page: int = 1, size: int = 20) -> tuple[List[Delivery], int]:
        """Get deliveries with filtering and pagination."""
        try:
            query = select(Delivery).options(selectinload(Delivery.driver))
            
            # Apply filters
            conditions = []
            if filters.status:
                conditions.append(Delivery.status == filters.status)
            if filters.priority:
                conditions.append(Delivery.priority == filters.priority)
            if filters.driver_id:
                conditions.append(Delivery.driver_id == uuid.UUID(filters.driver_id))
            if filters.customer_id:
                conditions.append(Delivery.customer_id == filters.customer_id)
            if filters.date_from:
                conditions.append(Delivery.created_at >= filters.date_from)
            if filters.date_to:
                conditions.append(Delivery.created_at <= filters.date_to)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            # Get total count
            count_query = select(func.count(Delivery.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            total_result = await db.execute(count_query)
            total = total_result.scalar()
            
            # Apply pagination
            offset = (page - 1) * size
            query = query.offset(offset).limit(size).order_by(Delivery.created_at.desc())
            
            result = await db.execute(query)
            deliveries = result.scalars().all()
            
            return list(deliveries), total
            
        except Exception as e:
            logger.error(f"Error getting deliveries: {e}")
            return [], 0

    async def assign_delivery(self, db: AsyncSession, assignment: DeliveryAssignment) -> bool:
        """Assign delivery to driver."""
        try:
            # Check if driver is available
            driver = await db.execute(
                select(Driver).where(
                    and_(
                        Driver.id == uuid.UUID(assignment.driver_id),
                        Driver.status == DriverStatus.AVAILABLE,
                        Driver.is_active == True
                    )
                )
            )
            driver = driver.scalar_one_or_none()
            if not driver:
                logger.warning(f"Driver {assignment.driver_id} not available")
                return False
            
            # Update delivery
            delivery = await self.get_delivery(db, assignment.delivery_id)
            if not delivery or delivery.status != DeliveryStatus.PENDING:
                logger.warning(f"Delivery {assignment.delivery_id} not available for assignment")
                return False
            
            delivery.driver_id = uuid.UUID(assignment.driver_id)
            delivery.status = DeliveryStatus.ASSIGNED
            delivery.estimated_pickup_time = assignment.estimated_pickup_time
            delivery.estimated_delivery_time = assignment.estimated_delivery_time
            delivery.updated_at = datetime.utcnow()
            
            # Update driver status
            driver.status = DriverStatus.BUSY
            driver.updated_at = datetime.utcnow()
            
            await db.commit()
            
            # Add tracking update
            await self.add_tracking_update(
                db, assignment.delivery_id,
                TrackingUpdate(status=DeliveryStatus.ASSIGNED),
                assignment.driver_id
            )
            
            logger.info(f"Assigned delivery {assignment.delivery_id} to driver {assignment.driver_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning delivery: {e}")
            await db.rollback()
            return False

    async def add_tracking_update(self, db: AsyncSession, delivery_id: str, 
                                update: TrackingUpdate, created_by: str) -> bool:
        """Add tracking update for delivery."""
        try:
            tracking = DeliveryTracking(
                delivery_id=uuid.UUID(delivery_id),
                status=update.status,
                location_lat=update.location_lat,
                location_lng=update.location_lng,
                notes=update.notes,
                created_by=created_by
            )
            
            db.add(tracking)
            
            # Update delivery status
            delivery = await self.get_delivery(db, delivery_id)
            if delivery:
                delivery.status = update.status
                delivery.updated_at = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Added tracking update for delivery {delivery_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding tracking update: {e}")
            await db.rollback()
            return False

    async def get_delivery_tracking(self, db: AsyncSession, delivery_id: str) -> List[DeliveryTracking]:
        """Get tracking history for delivery."""
        try:
            result = await db.execute(
                select(DeliveryTracking)
                .where(DeliveryTracking.delivery_id == uuid.UUID(delivery_id))
                .order_by(DeliveryTracking.timestamp.desc())
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting tracking for delivery {delivery_id}: {e}")
            return []

    async def _calculate_distance(self, lat1: float, lng1: float, 
                                lat2: float, lng2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        from math import radians, cos, sin, asin, sqrt
        
        # Convert to radians
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        c = 2 * asin(sqrt(a))
        
        # Radius of earth in kilometers
        r = 6371
        return c * r

    async def calculate_eta(self, pickup_lat: float, pickup_lng: float,
                          delivery_lat: float, delivery_lng: float,
                          priority: str = "NORMAL") -> Dict[str, Any]:
        """Calculate ETA for delivery."""
        try:
            distance_km = await self._calculate_distance(
                pickup_lat, pickup_lng, delivery_lat, delivery_lng
            )

            # Base travel time calculation
            travel_time_minutes = (distance_km / settings.AVERAGE_SPEED_KMH) * 60

            # Add buffer time
            buffer_minutes = settings.DELIVERY_BUFFER_MINUTES

            # Adjust for priority
            if priority == "URGENT":
                buffer_minutes = buffer_minutes // 2
            elif priority == "HIGH":
                buffer_minutes = int(buffer_minutes * 0.75)

            total_minutes = travel_time_minutes + buffer_minutes

            # Calculate pickup and delivery times
            now = datetime.utcnow()
            estimated_pickup_time = now + timedelta(minutes=15)  # 15 min prep time
            estimated_delivery_time = estimated_pickup_time + timedelta(minutes=total_minutes)

            return {
                "distance_km": round(distance_km, 2),
                "estimated_duration_minutes": int(total_minutes),
                "estimated_pickup_time": estimated_pickup_time,
                "estimated_delivery_time": estimated_delivery_time
            }

        except Exception as e:
            logger.error(f"Error calculating ETA: {e}")
            raise
