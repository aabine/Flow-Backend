from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.cylinder_service import CylinderService
from app.models.cylinder import Cylinder
from app.schemas.cylinder import (
    CylinderCreate, CylinderUpdate, CylinderResponse, CylinderSearchRequest, CylinderSearchResponse,
    CylinderMaintenanceCreate, CylinderMaintenanceUpdate, CylinderMaintenanceResponse,
    CylinderQualityCheckCreate, CylinderQualityCheckUpdate, CylinderQualityCheckResponse,
    CylinderLifecycleEventResponse, CylinderUsageLogCreate, CylinderUsageLogUpdate, CylinderUsageLogResponse,
    CylinderAllocationRequest, CylinderAllocationResponse,
    CylinderBatchCreate, CylinderBatchUpdate, CylinderBatchResponse,
    CylinderAnalyticsRequest, CylinderAnalyticsResponse
)
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=APIResponse)
async def create_cylinder(
    cylinder_data: CylinderCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new cylinder and register it in the system."""
    try:
        # Only vendors can create cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can create cylinders")
        
        cylinder_service = CylinderService()
        cylinder = await cylinder_service.create_cylinder(
            db, cylinder_data, current_user["user_id"]
        )
        
        return APIResponse(
            success=True,
            message="Cylinder created successfully",
            data={"cylinder_id": str(cylinder.id), "serial_number": cylinder.serial_number}
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating cylinder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create cylinder")


@router.get("/{cylinder_id}", response_model=CylinderResponse)
async def get_cylinder(
    cylinder_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get cylinder details by ID."""
    try:
        cylinder_service = CylinderService()
        
        # Vendors can only access their own cylinders
        if current_user["role"] == UserRole.VENDOR:
            cylinder = await cylinder_service.get_cylinder(db, cylinder_id, current_user["user_id"])
        elif current_user["role"] == UserRole.ADMIN:
            # Admins can access any cylinder
            result = await db.execute(
                select(Cylinder).where(Cylinder.id == cylinder_id)
            )
            cylinder = result.scalar_one_or_none()
        else:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not cylinder:
            raise HTTPException(status_code=404, detail="Cylinder not found")
        
        return cylinder

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cylinder {cylinder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cylinder")


@router.put("/{cylinder_id}", response_model=CylinderResponse)
async def update_cylinder(
    cylinder_id: str,
    cylinder_data: CylinderUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update cylinder information."""
    try:
        # Only vendors can update their cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can update cylinders")
        
        cylinder_service = CylinderService()
        cylinder = await cylinder_service.update_cylinder(
            db, cylinder_id, cylinder_data, current_user["user_id"], current_user["user_id"]
        )
        
        if not cylinder:
            raise HTTPException(status_code=404, detail="Cylinder not found")
        
        return cylinder

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating cylinder {cylinder_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update cylinder")


@router.post("/search", response_model=CylinderSearchResponse)
async def search_cylinders(
    search_request: CylinderSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search cylinders with filters and pagination."""
    try:
        cylinder_service = CylinderService()
        
        # Vendors can only search their own cylinders
        if current_user["role"] == UserRole.VENDOR:
            cylinders, total = await cylinder_service.search_cylinders(
                db, search_request, current_user["user_id"]
            )
        elif current_user["role"] == UserRole.ADMIN:
            # Admins can search all cylinders (remove vendor filter)
            cylinders, total = await cylinder_service.search_cylinders(
                db, search_request, None
            )
        else:
            raise HTTPException(status_code=403, detail="Access denied")
        
        total_pages = (total + search_request.page_size - 1) // search_request.page_size
        
        return CylinderSearchResponse(
            cylinders=cylinders,
            total=total,
            page=search_request.page,
            page_size=search_request.page_size,
            total_pages=total_pages,
            filters_applied=search_request.filters
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching cylinders: {e}")
        raise HTTPException(status_code=500, detail="Failed to search cylinders")


@router.post("/allocate", response_model=CylinderAllocationResponse)
async def allocate_cylinders(
    allocation_request: CylinderAllocationRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Allocate cylinders for an order using intelligent algorithms."""
    try:
        # Only hospitals can request cylinder allocation
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can request cylinder allocation")
        
        cylinder_service = CylinderService()
        allocation_response = await cylinder_service.allocate_cylinders(db, allocation_request)
        
        return allocation_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error allocating cylinders: {e}")
        raise HTTPException(status_code=500, detail="Failed to allocate cylinders")


@router.post("/reserve", response_model=APIResponse)
async def reserve_cylinders(
    cylinder_ids: List[str],
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reserve cylinders for an order."""
    try:
        # Only vendors can reserve their cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can reserve cylinders")
        
        cylinder_service = CylinderService()
        reserved_cylinders = await cylinder_service.reserve_cylinders(
            db, cylinder_ids, order_id, current_user["user_id"], current_user["user_id"]
        )
        
        return APIResponse(
            success=True,
            message=f"Reserved {len(reserved_cylinders)} cylinders for order {order_id}",
            data={"reserved_cylinder_ids": [str(c.id) for c in reserved_cylinders]}
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error reserving cylinders: {e}")
        raise HTTPException(status_code=500, detail="Failed to reserve cylinders")


@router.post("/release", response_model=APIResponse)
async def release_cylinders(
    cylinder_ids: List[str],
    reason: str = "Order cancelled",
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Release reserved cylinders back to available pool."""
    try:
        # Only vendors can release their cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can release cylinders")
        
        cylinder_service = CylinderService()
        released_cylinders = await cylinder_service.release_cylinders(
            db, cylinder_ids, current_user["user_id"], current_user["user_id"], reason
        )
        
        return APIResponse(
            success=True,
            message=f"Released {len(released_cylinders)} cylinders",
            data={"released_cylinder_ids": [str(c.id) for c in released_cylinders]}
        )

    except Exception as e:
        logger.error(f"Error releasing cylinders: {e}")
        raise HTTPException(status_code=500, detail="Failed to release cylinders")


# Maintenance Management Endpoints
@router.post("/{cylinder_id}/maintenance", response_model=CylinderMaintenanceResponse)
async def schedule_maintenance(
    cylinder_id: str,
    maintenance_data: CylinderMaintenanceCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Schedule maintenance for a cylinder."""
    try:
        # Only vendors can schedule maintenance for their cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can schedule maintenance")
        
        # Override cylinder_id from URL
        maintenance_data.cylinder_id = cylinder_id
        
        cylinder_service = CylinderService()
        maintenance = await cylinder_service.schedule_maintenance(
            db, maintenance_data, current_user["user_id"], current_user["user_id"]
        )
        
        return maintenance

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scheduling maintenance: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule maintenance")


@router.put("/maintenance/{maintenance_id}", response_model=CylinderMaintenanceResponse)
async def complete_maintenance(
    maintenance_id: str,
    maintenance_data: CylinderMaintenanceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Complete maintenance and update cylinder status."""
    try:
        # Only vendors can complete maintenance
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can complete maintenance")
        
        cylinder_service = CylinderService()
        maintenance = await cylinder_service.complete_maintenance(
            db, maintenance_id, maintenance_data, current_user["user_id"], current_user["user_id"]
        )
        
        if not maintenance:
            raise HTTPException(status_code=404, detail="Maintenance record not found")
        
        return maintenance

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing maintenance: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete maintenance")


# Quality Control Endpoints
@router.post("/{cylinder_id}/quality-checks", response_model=CylinderQualityCheckResponse)
async def create_quality_check(
    cylinder_id: str,
    quality_data: CylinderQualityCheckCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a quality control check for a cylinder."""
    try:
        # Only vendors can create quality checks for their cylinders
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can create quality checks")
        
        # Override cylinder_id from URL
        quality_data.cylinder_id = cylinder_id
        
        cylinder_service = CylinderService()
        quality_check = await cylinder_service.create_quality_check(
            db, quality_data, current_user["user_id"], current_user["user_id"]
        )
        
        return quality_check

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating quality check: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quality check")
