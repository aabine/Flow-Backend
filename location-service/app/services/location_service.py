from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.location import Location, EmergencyZone, ServiceArea
from app.schemas.location import LocationCreate, LocationUpdate, NearbySearchRequest
from shared.models import UserRole


class LocationService:
    """Service for managing location operations."""
    
    async def create_location(
        self, 
        db: AsyncSession, 
        user_id: str,
        location_data: LocationCreate
    ) -> Location:
        """Create a new location."""
        location = Location(
            user_id=user_id,
            name=location_data.name,
            address=location_data.address,
            city=location_data.city,
            state=location_data.state,
            country=location_data.country,
            latitude=location_data.latitude,
            longitude=location_data.longitude,
            location_type=location_data.location_type
        )
        
        db.add(location)
        await db.commit()
        await db.refresh(location)
        return location
    
    async def get_location(
        self, 
        db: AsyncSession, 
        location_id: str
    ) -> Optional[Location]:
        """Get location by ID."""
        result = await db.execute(
            select(Location).where(Location.id == location_id)
        )
        return result.scalar_one_or_none()
    
    async def search_nearby_locations(
        self,
        db: AsyncSession,
        search_request: NearbySearchRequest
    ) -> List[Location]:
        """Search for nearby locations."""
        # Calculate distance using Haversine formula (simplified)
        distance_formula = func.sqrt(
            func.pow(69.1 * (Location.latitude - search_request.latitude), 2) +
            func.pow(69.1 * (search_request.longitude - Location.longitude) * 
                    func.cos(Location.latitude / 57.3), 2)
        )
        
        query = select(Location).where(
            and_(
                Location.is_active == True,
                distance_formula <= search_request.radius_km
            )
        )
        
        if search_request.location_type:
            query = query.where(Location.location_type == search_request.location_type)
        
        result = await db.execute(query.order_by(distance_formula))
        return result.scalars().all()
    
    async def get_nearby_vendors(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0
    ) -> List[Location]:
        """Get vendors within radius of location."""
        distance_formula = func.sqrt(
            func.pow(69.1 * (Location.latitude - latitude), 2) +
            func.pow(69.1 * (longitude - Location.longitude) * 
                    func.cos(Location.latitude / 57.3), 2)
        )
        
        result = await db.execute(
            select(Location)
            .where(and_(
                Location.is_active == True,
                Location.location_type == 'vendor',
                distance_formula <= radius_km
            ))
            .order_by(distance_formula)
        )
        return result.scalars().all()
    
    async def get_nearby_hospitals(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0
    ) -> List[Location]:
        """Get hospitals within radius of location."""
        distance_formula = func.sqrt(
            func.pow(69.1 * (Location.latitude - latitude), 2) +
            func.pow(69.1 * (longitude - Location.longitude) * 
                    func.cos(Location.latitude / 57.3), 2)
        )
        
        result = await db.execute(
            select(Location)
            .where(and_(
                Location.is_active == True,
                Location.location_type == 'hospital',
                distance_formula <= radius_km
            ))
            .order_by(distance_formula)
        )
        return result.scalars().all()
    
    async def update_location_coordinates(
        self,
        db: AsyncSession,
        location_id: str,
        latitude: float,
        longitude: float,
        user_id: str
    ) -> Optional[Location]:
        """Update location coordinates."""
        result = await db.execute(
            select(Location).where(and_(
                Location.id == location_id,
                Location.user_id == user_id
            ))
        )
        location = result.scalar_one_or_none()
        
        if location:
            location.latitude = latitude
            location.longitude = longitude
            await db.commit()
            await db.refresh(location)
        
        return location
    
    async def get_vendor_service_areas(
        self,
        db: AsyncSession,
        vendor_id: str
    ) -> List[ServiceArea]:
        """Get vendor's service areas."""
        result = await db.execute(
            select(ServiceArea)
            .where(and_(
                ServiceArea.vendor_id == vendor_id,
                ServiceArea.is_active == True
            ))
        )
        return result.scalars().all()
    
    async def create_service_area(
        self,
        db: AsyncSession,
        vendor_id: str,
        area_data: Dict[str, Any]
    ) -> ServiceArea:
        """Create service area for vendor."""
        service_area = ServiceArea(
            vendor_id=vendor_id,
            name=area_data['name'],
            center_latitude=area_data['center_latitude'],
            center_longitude=area_data['center_longitude'],
            radius_km=area_data['radius_km'],
            delivery_fee=area_data.get('delivery_fee', 0.0),
            minimum_order_amount=area_data.get('minimum_order_amount', 0.0)
        )
        
        db.add(service_area)
        await db.commit()
        await db.refresh(service_area)
        return service_area
