from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import get_db
from app.models.location import Location, EmergencyZone, ServiceArea
from app.schemas.location import (
    LocationCreate, LocationResponse, LocationUpdate,
    EmergencyZoneCreate, EmergencyZoneResponse,
    ServiceAreaCreate, ServiceAreaResponse,
    NearbySearchRequest, NearbySearchResponse
)
from app.services.location_service import LocationService
from app.services.emergency_service import EmergencyService
from shared.models import UserRole, APIResponse

app = FastAPI(
    title="Location Service",
    description="Geospatial location management and emergency zone service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

location_service = LocationService()
emergency_service = EmergencyService()


def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required"
        )
    return {"user_id": x_user_id, "role": x_user_role}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Location Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/locations", response_model=APIResponse)
async def create_location(
    location_data: LocationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new location."""
    try:
        location = await location_service.create_location(
            db, current_user["user_id"], location_data
        )
        
        return APIResponse(
            success=True,
            message="Location created successfully",
            data={
                "location_id": str(location.id),
                "name": location.name,
                "coordinates": {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create location: {str(e)}"
        )


@app.get("/locations/{location_id}", response_model=LocationResponse)
async def get_location(
    location_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get location by ID."""
    try:
        location = await location_service.get_location_by_id(db, location_id)
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Location not found"
            )
        
        return LocationResponse.from_orm(location)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get location: {str(e)}"
        )


@app.post("/locations/search/nearby", response_model=NearbySearchResponse)
async def search_nearby_locations(
    search_request: NearbySearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search for nearby locations."""
    try:
        results = await location_service.search_nearby_locations(
            db, 
            search_request.latitude,
            search_request.longitude,
            search_request.radius_km,
            search_request.location_type,
            search_request.user_role
        )
        
        return NearbySearchResponse(
            search_center={
                "latitude": search_request.latitude,
                "longitude": search_request.longitude
            },
            radius_km=search_request.radius_km,
            results=results,
            total_results=len(results)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search nearby locations: {str(e)}"
        )


@app.post("/emergency-zones", response_model=APIResponse)
async def create_emergency_zone(
    zone_data: EmergencyZoneCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create emergency zone (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        zone = await emergency_service.create_emergency_zone(db, zone_data)
        
        return APIResponse(
            success=True,
            message="Emergency zone created successfully",
            data={
                "zone_id": str(zone.id),
                "name": zone.name,
                "status": zone.status
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create emergency zone: {str(e)}"
        )


@app.get("/emergency-zones")
async def get_emergency_zones(
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get emergency zones."""
    try:
        zones = await emergency_service.get_emergency_zones(db, active_only)
        
        return {
            "zones": [EmergencyZoneResponse.from_orm(zone) for zone in zones],
            "total": len(zones)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emergency zones: {str(e)}"
        )


@app.post("/emergency-zones/{zone_id}/activate", response_model=APIResponse)
async def activate_emergency_zone(
    zone_id: str,
    alert_message: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Activate emergency zone and send alerts."""
    try:
        if current_user["role"] not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or hospital access required"
            )
        
        # Activate zone and get affected users
        affected_users = await emergency_service.activate_emergency_zone(
            db, zone_id, alert_message, current_user["user_id"]
        )
        
        return APIResponse(
            success=True,
            message="Emergency zone activated successfully",
            data={
                "zone_id": zone_id,
                "affected_users": len(affected_users),
                "alert_sent": True
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate emergency zone: {str(e)}"
        )


@app.post("/emergency-zones/{zone_id}/deactivate", response_model=APIResponse)
async def deactivate_emergency_zone(
    zone_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate emergency zone."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        await emergency_service.deactivate_emergency_zone(db, zone_id)
        
        return APIResponse(
            success=True,
            message="Emergency zone deactivated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate emergency zone: {str(e)}"
        )


@app.get("/service-areas/vendor/{vendor_id}")
async def get_vendor_service_areas(
    vendor_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor's service areas."""
    try:
        # Check access permissions
        if (current_user["role"] == UserRole.VENDOR and 
            current_user["user_id"] != vendor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        service_areas = await location_service.get_vendor_service_areas(db, vendor_id)
        
        return {
            "vendor_id": vendor_id,
            "service_areas": [ServiceAreaResponse.from_orm(area) for area in service_areas],
            "total": len(service_areas)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get service areas: {str(e)}"
        )


@app.post("/service-areas", response_model=APIResponse)
async def create_service_area(
    area_data: ServiceAreaCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create service area (vendor only)."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create service areas"
            )
        
        service_area = await location_service.create_service_area(
            db, current_user["user_id"], area_data
        )
        
        return APIResponse(
            success=True,
            message="Service area created successfully",
            data={
                "area_id": str(service_area.id),
                "name": service_area.name,
                "radius_km": service_area.radius_km
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create service area: {str(e)}"
        )


@app.get("/vendors/nearby")
async def get_nearby_vendors(
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendors within radius of location."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can search for vendors"
            )
        
        vendors = await location_service.get_nearby_vendors(
            db, latitude, longitude, radius_km
        )
        
        return {
            "search_location": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "vendors": vendors,
            "total": len(vendors)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get nearby vendors: {str(e)}"
        )


@app.get("/hospitals/nearby")
async def get_nearby_hospitals(
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get hospitals within radius of location."""
    try:
        hospitals = await location_service.get_nearby_hospitals(
            db, latitude, longitude, radius_km
        )
        
        return {
            "search_location": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "hospitals": hospitals,
            "total": len(hospitals)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get nearby hospitals: {str(e)}"
        )


@app.post("/locations/{location_id}/update-coordinates", response_model=APIResponse)
async def update_location_coordinates(
    location_id: str,
    latitude: float,
    longitude: float,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update location coordinates."""
    try:
        location = await location_service.update_location_coordinates(
            db, location_id, latitude, longitude, current_user["user_id"]
        )
        
        return APIResponse(
            success=True,
            message="Location coordinates updated successfully",
            data={
                "location_id": location_id,
                "new_coordinates": {
                    "latitude": location.latitude,
                    "longitude": location.longitude
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update location coordinates: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
