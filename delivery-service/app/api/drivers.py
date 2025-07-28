from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.driver_service import DriverService
from app.schemas.delivery import DriverCreate, DriverUpdate, DriverResponse
from shared.models import APIResponse
from shared.security.auth import get_current_user

router = APIRouter()
driver_service = DriverService()


@router.post("/", response_model=APIResponse)
async def create_driver(
    driver_data: DriverCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new driver."""
    try:
        driver = await driver_service.create_driver(db, driver_data)
        
        return APIResponse(
            success=True,
            message="Driver created successfully",
            data={"driver_id": str(driver.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create driver")


@router.get("/", response_model=List[DriverResponse])
async def get_drivers(
    status: Optional[str] = Query(None),
    vehicle_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all drivers with optional filtering."""
    try:
        # TODO: Implement filtering in driver service
        # For now, return empty list as placeholder
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch drivers")


@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get driver by ID."""
    try:
        driver = await driver_service.get_driver(db, driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return DriverResponse.from_orm(driver)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch driver")


@router.put("/{driver_id}", response_model=APIResponse)
async def update_driver(
    driver_id: str,
    driver_data: DriverUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update driver."""
    try:
        driver = await driver_service.update_driver(db, driver_id, driver_data)
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return APIResponse(
            success=True,
            message="Driver updated successfully",
            data={"driver_id": driver_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update driver")


@router.post("/{driver_id}/location", response_model=APIResponse)
async def update_driver_location(
    driver_id: str,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update driver location."""
    try:
        success = await driver_service.update_driver_location(db, driver_id, lat, lng)
        if not success:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return APIResponse(
            success=True,
            message="Driver location updated successfully",
            data={"driver_id": driver_id, "lat": lat, "lng": lng}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update driver location")


@router.get("/{driver_id}/stats", response_model=Dict[str, Any])
async def get_driver_stats(
    driver_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get driver statistics."""
    try:
        stats = await driver_service.get_driver_stats(db, driver_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch driver stats")


@router.get("/available/near", response_model=List[DriverResponse])
async def get_available_drivers_near(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    max_distance_km: Optional[float] = Query(None, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get available drivers near a location."""
    try:
        drivers = await driver_service.get_available_drivers(db, lat, lng, max_distance_km)
        return [DriverResponse.from_orm(driver) for driver in drivers]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch available drivers")


@router.get("/user/{user_id}", response_model=DriverResponse)
async def get_driver_by_user_id(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get driver by user ID."""
    try:
        driver = await driver_service.get_driver_by_user_id(db, user_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        
        return DriverResponse.from_orm(driver)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch driver")
