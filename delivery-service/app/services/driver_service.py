from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging

from app.models.delivery import Driver, Delivery, DriverStatus, DeliveryStatus
from app.schemas.delivery import DriverCreate, DriverUpdate
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DriverService:
    """Service for managing drivers."""

    async def create_driver(self, db: AsyncSession, driver_data: DriverCreate) -> Driver:
        """Create a new driver."""
        try:
            driver = Driver(
                user_id=driver_data.user_id,
                driver_license=driver_data.driver_license,
                phone_number=driver_data.phone_number,
                vehicle_type=driver_data.vehicle_type,
                vehicle_plate=driver_data.vehicle_plate,
                vehicle_capacity=driver_data.vehicle_capacity
            )
            
            db.add(driver)
            await db.commit()
            await db.refresh(driver)
            
            logger.info(f"Created driver {driver.id} for user {driver.user_id}")
            return driver
            
        except Exception as e:
            logger.error(f"Error creating driver: {e}")
            await db.rollback()
            raise

    async def get_driver(self, db: AsyncSession, driver_id: str) -> Optional[Driver]:
        """Get driver by ID."""
        try:
            result = await db.execute(
                select(Driver).where(Driver.id == uuid.UUID(driver_id))
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting driver {driver_id}: {e}")
            return None

    async def get_driver_by_user_id(self, db: AsyncSession, user_id: str) -> Optional[Driver]:
        """Get driver by user ID."""
        try:
            result = await db.execute(
                select(Driver).where(Driver.user_id == user_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting driver for user {user_id}: {e}")
            return None

    async def update_driver(self, db: AsyncSession, driver_id: str, 
                          driver_data: DriverUpdate) -> Optional[Driver]:
        """Update driver."""
        try:
            driver = await self.get_driver(db, driver_id)
            if not driver:
                return None
            
            update_data = driver_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(driver, field, value)
            
            driver.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(driver)
            
            logger.info(f"Updated driver {driver_id}")
            return driver
            
        except Exception as e:
            logger.error(f"Error updating driver {driver_id}: {e}")
            await db.rollback()
            raise

    async def update_driver_location(self, db: AsyncSession, driver_id: str, 
                                   lat: float, lng: float) -> bool:
        """Update driver location."""
        try:
            driver = await self.get_driver(db, driver_id)
            if not driver:
                return False
            
            driver.current_location_lat = lat
            driver.current_location_lng = lng
            driver.updated_at = datetime.utcnow()
            
            await db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating driver location: {e}")
            await db.rollback()
            return False

    async def get_available_drivers(self, db: AsyncSession, 
                                  pickup_lat: float, pickup_lng: float,
                                  max_distance_km: float = None) -> List[Driver]:
        """Get available drivers near pickup location."""
        try:
            if max_distance_km is None:
                max_distance_km = settings.DEFAULT_DELIVERY_RADIUS_KM
            
            # Get all available drivers
            result = await db.execute(
                select(Driver).where(
                    and_(
                        Driver.status == DriverStatus.AVAILABLE,
                        Driver.is_active == True,
                        Driver.current_location_lat.isnot(None),
                        Driver.current_location_lng.isnot(None)
                    )
                )
            )
            drivers = list(result.scalars().all())
            
            # Filter by distance and sort by proximity
            nearby_drivers = []
            for driver in drivers:
                distance = await self._calculate_distance(
                    pickup_lat, pickup_lng,
                    driver.current_location_lat, driver.current_location_lng
                )
                if distance <= max_distance_km:
                    nearby_drivers.append((driver, distance))
            
            # Sort by distance (closest first)
            nearby_drivers.sort(key=lambda x: x[1])
            
            return [driver for driver, _ in nearby_drivers]
            
        except Exception as e:
            logger.error(f"Error getting available drivers: {e}")
            return []

    async def find_best_driver(self, db: AsyncSession, delivery_lat: float, delivery_lng: float,
                             cylinder_size: str, quantity: int) -> Optional[Driver]:
        """Find the best driver for a delivery based on multiple factors."""
        try:
            available_drivers = await self.get_available_drivers(db, delivery_lat, delivery_lng)
            
            if not available_drivers:
                return None
            
            # Score drivers based on multiple factors
            scored_drivers = []
            for driver in available_drivers:
                # Check capacity
                if driver.vehicle_capacity < quantity:
                    continue
                
                # Calculate distance score (closer is better)
                distance = await self._calculate_distance(
                    delivery_lat, delivery_lng,
                    driver.current_location_lat, driver.current_location_lng
                )
                distance_score = max(0, 100 - (distance * 2))  # Penalty for distance
                
                # Rating score (higher rating is better)
                rating_score = driver.rating * 20  # Scale to 0-100
                
                # Experience score (more deliveries is better)
                experience_score = min(100, driver.total_deliveries * 2)
                
                # Combined score (weighted average)
                total_score = (
                    distance_score * 0.4 +
                    rating_score * 0.4 +
                    experience_score * 0.2
                )
                
                scored_drivers.append((driver, total_score, distance))
            
            if not scored_drivers:
                return None
            
            # Sort by score (highest first)
            scored_drivers.sort(key=lambda x: x[1], reverse=True)
            
            logger.info(f"Found {len(scored_drivers)} suitable drivers, selected best one")
            return scored_drivers[0][0]
            
        except Exception as e:
            logger.error(f"Error finding best driver: {e}")
            return None

    async def get_driver_stats(self, db: AsyncSession, driver_id: str) -> Dict[str, Any]:
        """Get driver statistics."""
        try:
            driver = await self.get_driver(db, driver_id)
            if not driver:
                return {}
            
            # Get delivery statistics
            today = datetime.utcnow().date()
            
            # Today's deliveries
            today_deliveries = await db.execute(
                select(func.count(Delivery.id)).where(
                    and_(
                        Delivery.driver_id == uuid.UUID(driver_id),
                        func.date(Delivery.created_at) == today
                    )
                )
            )
            today_count = today_deliveries.scalar() or 0
            
            # Completed deliveries
            completed_deliveries = await db.execute(
                select(func.count(Delivery.id)).where(
                    and_(
                        Delivery.driver_id == uuid.UUID(driver_id),
                        Delivery.status == DeliveryStatus.DELIVERED
                    )
                )
            )
            completed_count = completed_deliveries.scalar() or 0
            
            # Active deliveries
            active_deliveries = await db.execute(
                select(func.count(Delivery.id)).where(
                    and_(
                        Delivery.driver_id == uuid.UUID(driver_id),
                        Delivery.status.in_([
                            DeliveryStatus.ASSIGNED,
                            DeliveryStatus.PICKED_UP,
                            DeliveryStatus.IN_TRANSIT,
                            DeliveryStatus.OUT_FOR_DELIVERY
                        ])
                    )
                )
            )
            active_count = active_deliveries.scalar() or 0
            
            return {
                "driver_id": driver_id,
                "total_deliveries": driver.total_deliveries,
                "today_deliveries": today_count,
                "completed_deliveries": completed_count,
                "active_deliveries": active_count,
                "rating": driver.rating,
                "status": driver.status.value,
                "vehicle_type": driver.vehicle_type.value,
                "vehicle_capacity": driver.vehicle_capacity
            }
            
        except Exception as e:
            logger.error(f"Error getting driver stats: {e}")
            return {}

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
