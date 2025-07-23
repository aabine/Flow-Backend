from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.location import EmergencyZone
from app.schemas.location import EmergencyZoneCreate


class EmergencyService:
    """Service for managing emergency zones and alerts."""
    
    async def create_emergency_zone(
        self,
        db: AsyncSession,
        zone_data: EmergencyZoneCreate,
        created_by: str
    ) -> EmergencyZone:
        """Create a new emergency zone."""
        zone = EmergencyZone(
            name=zone_data.name,
            description=zone_data.description,
            center_latitude=zone_data.center_latitude,
            center_longitude=zone_data.center_longitude,
            radius_km=zone_data.radius_km,
            severity_level=zone_data.severity_level,
            alert_message=zone_data.alert_message,
            created_by=created_by
        )
        
        db.add(zone)
        await db.commit()
        await db.refresh(zone)
        return zone
    
    async def get_emergency_zones(
        self,
        db: AsyncSession,
        active_only: bool = True
    ) -> List[EmergencyZone]:
        """Get emergency zones."""
        query = select(EmergencyZone)
        
        if active_only:
            query = query.where(EmergencyZone.is_active == True)
        
        result = await db.execute(query.order_by(EmergencyZone.created_at.desc()))
        return result.scalars().all()
    
    async def activate_emergency_zone(
        self,
        db: AsyncSession,
        zone_id: str,
        alert_message: str,
        activated_by: str
    ) -> Optional[EmergencyZone]:
        """Activate emergency zone and send alerts."""
        result = await db.execute(
            select(EmergencyZone).where(EmergencyZone.id == zone_id)
        )
        zone = result.scalar_one_or_none()
        
        if zone:
            zone.is_active = True
            zone.alert_message = alert_message
            zone.activated_at = datetime.utcnow()
            zone.deactivated_at = None
            
            await db.commit()
            await db.refresh(zone)
            
            # TODO: Send emergency alerts to affected users
            # This would integrate with notification service
        
        return zone
    
    async def deactivate_emergency_zone(
        self,
        db: AsyncSession,
        zone_id: str,
        deactivated_by: str
    ) -> Optional[EmergencyZone]:
        """Deactivate emergency zone."""
        result = await db.execute(
            select(EmergencyZone).where(EmergencyZone.id == zone_id)
        )
        zone = result.scalar_one_or_none()
        
        if zone:
            zone.is_active = False
            zone.deactivated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(zone)
        
        return zone
    
    async def check_location_in_emergency_zones(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float
    ) -> List[EmergencyZone]:
        """Check if location is within any active emergency zones."""
        # Calculate distance using Haversine formula (simplified)
        distance_formula = func.sqrt(
            func.pow(69.1 * (EmergencyZone.center_latitude - latitude), 2) +
            func.pow(69.1 * (longitude - EmergencyZone.center_longitude) * 
                    func.cos(EmergencyZone.center_latitude / 57.3), 2)
        )
        
        result = await db.execute(
            select(EmergencyZone)
            .where(and_(
                EmergencyZone.is_active == True,
                distance_formula <= EmergencyZone.radius_km
            ))
            .order_by(EmergencyZone.severity_level.desc())
        )
        return result.scalars().all()
