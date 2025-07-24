from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Dict, Any, Tuple
from datetime import datetime
import uuid
import logging
import json

from app.models.delivery import DeliveryRoute, Delivery, Driver
from app.schemas.delivery import RouteCreate
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RouteService:
    """Service for route optimization and management."""

    async def create_route(self, db: AsyncSession, route_data: RouteCreate) -> DeliveryRoute:
        """Create optimized route for deliveries."""
        try:
            # Get deliveries
            delivery_ids = [uuid.UUID(did) for did in route_data.delivery_ids]
            result = await db.execute(
                select(Delivery).where(Delivery.id.in_(delivery_ids))
            )
            deliveries = list(result.scalars().all())
            
            if not deliveries:
                raise ValueError("No valid deliveries found")
            
            # Get driver
            driver_result = await db.execute(
                select(Driver).where(Driver.id == uuid.UUID(route_data.driver_id))
            )
            driver = driver_result.scalar_one_or_none()
            if not driver:
                raise ValueError("Driver not found")
            
            # Optimize route
            optimized_deliveries, total_distance, estimated_duration, waypoints = await self._optimize_route(
                deliveries, driver.current_location_lat, driver.current_location_lng
            )
            
            # Create route name if not provided
            route_name = route_data.route_name or f"Route_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            route = DeliveryRoute(
                driver_id=uuid.UUID(route_data.driver_id),
                route_name=route_name,
                delivery_ids=[str(d.id) for d in optimized_deliveries],
                total_distance_km=total_distance,
                estimated_duration_minutes=estimated_duration,
                optimized_waypoints=waypoints
            )
            
            db.add(route)
            await db.commit()
            await db.refresh(route)
            
            logger.info(f"Created optimized route {route.id} with {len(deliveries)} deliveries")
            return route
            
        except Exception as e:
            logger.error(f"Error creating route: {e}")
            await db.rollback()
            raise

    async def get_route(self, db: AsyncSession, route_id: str) -> DeliveryRoute:
        """Get route by ID."""
        try:
            result = await db.execute(
                select(DeliveryRoute).where(DeliveryRoute.id == uuid.UUID(route_id))
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting route {route_id}: {e}")
            return None

    async def start_route(self, db: AsyncSession, route_id: str) -> bool:
        """Start route execution."""
        try:
            route = await self.get_route(db, route_id)
            if not route or route.status != "PLANNED":
                return False
            
            route.status = "ACTIVE"
            route.started_at = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Started route {route_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting route: {e}")
            await db.rollback()
            return False

    async def complete_route(self, db: AsyncSession, route_id: str) -> bool:
        """Complete route execution."""
        try:
            route = await self.get_route(db, route_id)
            if not route or route.status != "ACTIVE":
                return False
            
            route.status = "COMPLETED"
            route.completed_at = datetime.utcnow()
            
            await db.commit()
            logger.info(f"Completed route {route_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error completing route: {e}")
            await db.rollback()
            return False

    async def get_driver_routes(self, db: AsyncSession, driver_id: str, 
                              status: str = None) -> List[DeliveryRoute]:
        """Get routes for a driver."""
        try:
            query = select(DeliveryRoute).where(DeliveryRoute.driver_id == uuid.UUID(driver_id))
            
            if status:
                query = query.where(DeliveryRoute.status == status)
            
            query = query.order_by(DeliveryRoute.created_at.desc())
            
            result = await db.execute(query)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(f"Error getting driver routes: {e}")
            return []

    async def _optimize_route(self, deliveries: List[Delivery], start_lat: float, start_lng: float) -> Tuple[List[Delivery], float, int, List[Dict]]:
        """Optimize delivery route using nearest neighbor algorithm."""
        try:
            if not deliveries:
                return [], 0.0, 0, []
            
            if len(deliveries) == 1:
                delivery = deliveries[0]
                distance = await self._calculate_distance(
                    start_lat, start_lng, delivery.pickup_lat, delivery.pickup_lng
                )
                distance += await self._calculate_distance(
                    delivery.pickup_lat, delivery.pickup_lng,
                    delivery.delivery_lat, delivery.delivery_lng
                )
                
                waypoints = [
                    {"lat": start_lat, "lng": start_lng, "type": "start"},
                    {"lat": delivery.pickup_lat, "lng": delivery.pickup_lng, "type": "pickup", "delivery_id": str(delivery.id)},
                    {"lat": delivery.delivery_lat, "lng": delivery.delivery_lng, "type": "delivery", "delivery_id": str(delivery.id)}
                ]
                
                duration = int((distance / settings.AVERAGE_SPEED_KMH) * 60)
                return [delivery], distance, duration, waypoints
            
            # Nearest neighbor algorithm for multiple deliveries
            optimized_order = []
            remaining_deliveries = deliveries.copy()
            current_lat, current_lng = start_lat, start_lng
            total_distance = 0.0
            waypoints = [{"lat": start_lat, "lng": start_lng, "type": "start"}]
            
            while remaining_deliveries:
                # Find nearest pickup location
                nearest_delivery = None
                nearest_distance = float('inf')
                
                for delivery in remaining_deliveries:
                    distance = await self._calculate_distance(
                        current_lat, current_lng, delivery.pickup_lat, delivery.pickup_lng
                    )
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_delivery = delivery
                
                if nearest_delivery:
                    # Move to pickup location
                    total_distance += nearest_distance
                    waypoints.append({
                        "lat": nearest_delivery.pickup_lat,
                        "lng": nearest_delivery.pickup_lng,
                        "type": "pickup",
                        "delivery_id": str(nearest_delivery.id)
                    })
                    
                    # Move to delivery location
                    delivery_distance = await self._calculate_distance(
                        nearest_delivery.pickup_lat, nearest_delivery.pickup_lng,
                        nearest_delivery.delivery_lat, nearest_delivery.delivery_lng
                    )
                    total_distance += delivery_distance
                    waypoints.append({
                        "lat": nearest_delivery.delivery_lat,
                        "lng": nearest_delivery.delivery_lng,
                        "type": "delivery",
                        "delivery_id": str(nearest_delivery.id)
                    })
                    
                    # Update current position
                    current_lat, current_lng = nearest_delivery.delivery_lat, nearest_delivery.delivery_lng
                    
                    optimized_order.append(nearest_delivery)
                    remaining_deliveries.remove(nearest_delivery)
            
            # Calculate estimated duration
            estimated_duration = int((total_distance / settings.AVERAGE_SPEED_KMH) * 60)
            # Add buffer time for each delivery
            estimated_duration += len(deliveries) * settings.DELIVERY_BUFFER_MINUTES
            
            logger.info(f"Optimized route: {len(deliveries)} deliveries, {total_distance:.2f}km, {estimated_duration}min")
            return optimized_order, round(total_distance, 2), estimated_duration, waypoints
            
        except Exception as e:
            logger.error(f"Error optimizing route: {e}")
            return deliveries, 0.0, 0, []

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

    async def get_route_progress(self, db: AsyncSession, route_id: str) -> Dict[str, Any]:
        """Get route progress information."""
        try:
            route = await self.get_route(db, route_id)
            if not route:
                return {}
            
            # Get delivery statuses
            delivery_ids = [uuid.UUID(did) for did in route.delivery_ids]
            result = await db.execute(
                select(Delivery).where(Delivery.id.in_(delivery_ids))
            )
            deliveries = list(result.scalars().all())
            
            completed = sum(1 for d in deliveries if d.status.value == "DELIVERED")
            in_progress = sum(1 for d in deliveries if d.status.value in ["ASSIGNED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY"])
            pending = sum(1 for d in deliveries if d.status.value == "PENDING")
            
            progress_percentage = (completed / len(deliveries)) * 100 if deliveries else 0
            
            return {
                "route_id": route_id,
                "status": route.status,
                "total_deliveries": len(deliveries),
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "progress_percentage": round(progress_percentage, 2),
                "total_distance_km": route.total_distance_km,
                "estimated_duration_minutes": route.estimated_duration_minutes,
                "started_at": route.started_at,
                "completed_at": route.completed_at
            }
            
        except Exception as e:
            logger.error(f"Error getting route progress: {e}")
            return {}
