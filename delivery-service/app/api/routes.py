from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.route_service import RouteService
from app.schemas.delivery import RouteCreate, RouteResponse
from shared.models import APIResponse
from shared.security.auth import get_current_user

router = APIRouter()
route_service = RouteService()


@router.post("/", response_model=APIResponse)
async def create_route(
    route_data: RouteCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create optimized route for deliveries."""
    try:
        route = await route_service.create_route(db, route_data)
        
        return APIResponse(
            success=True,
            message="Route created successfully",
            data={"route_id": str(route.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create route")


@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get route by ID."""
    try:
        route = await route_service.get_route(db, route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")
        
        return RouteResponse.from_orm(route)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch route")


@router.post("/{route_id}/start", response_model=APIResponse)
async def start_route(
    route_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Start route execution."""
    try:
        success = await route_service.start_route(db, route_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot start route")
        
        return APIResponse(
            success=True,
            message="Route started successfully",
            data={"route_id": route_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to start route")


@router.post("/{route_id}/complete", response_model=APIResponse)
async def complete_route(
    route_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Complete route execution."""
    try:
        success = await route_service.complete_route(db, route_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot complete route")
        
        return APIResponse(
            success=True,
            message="Route completed successfully",
            data={"route_id": route_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to complete route")


@router.get("/driver/{driver_id}", response_model=List[RouteResponse])
async def get_driver_routes(
    driver_id: str,
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get routes for a driver."""
    try:
        routes = await route_service.get_driver_routes(db, driver_id, status)
        return [RouteResponse.from_orm(route) for route in routes]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch driver routes")


@router.get("/{route_id}/progress", response_model=Dict[str, Any])
async def get_route_progress(
    route_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get route progress information."""
    try:
        progress = await route_service.get_route_progress(db, route_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Route not found")
        
        return progress
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch route progress")
