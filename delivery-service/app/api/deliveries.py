from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.delivery_service import DeliveryService
from app.services.driver_service import DriverService
from app.schemas.delivery import (
    DeliveryCreate, DeliveryUpdate, DeliveryResponse, DeliveryFilters,
    PaginatedDeliveryResponse, TrackingUpdate, TrackingResponse,
    DeliveryAssignment, ETARequest, ETAResponse
)
from shared.models import APIResponse
from shared.security.auth import get_current_user

router = APIRouter()
delivery_service = DeliveryService()
driver_service = DriverService()


@router.post("/", response_model=APIResponse)
async def create_delivery(
    delivery_data: DeliveryCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new delivery."""
    try:
        delivery = await delivery_service.create_delivery(db, delivery_data)
        
        # TODO: Send notification to customer
        # background_tasks.add_task(send_delivery_notification, delivery.id)
        
        return APIResponse(
            success=True,
            message="Delivery created successfully",
            data={"delivery_id": str(delivery.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create delivery")


@router.get("/", response_model=PaginatedDeliveryResponse)
async def get_deliveries(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    driver_id: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get deliveries with filtering and pagination."""
    try:
        filters = DeliveryFilters(
            status=status,
            priority=priority,
            driver_id=driver_id,
            customer_id=customer_id
        )
        
        deliveries, total = await delivery_service.get_deliveries(db, filters, page, size)
        pages = (total + size - 1) // size
        
        return PaginatedDeliveryResponse(
            items=[DeliveryResponse.from_orm(delivery) for delivery in deliveries],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch deliveries")


@router.get("/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(
    delivery_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get delivery by ID."""
    try:
        delivery = await delivery_service.get_delivery(db, delivery_id)
        if not delivery:
            raise HTTPException(status_code=404, detail="Delivery not found")
        
        return DeliveryResponse.from_orm(delivery)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch delivery")


@router.put("/{delivery_id}", response_model=APIResponse)
async def update_delivery(
    delivery_id: str,
    delivery_data: DeliveryUpdate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update delivery."""
    try:
        delivery = await delivery_service.update_delivery(db, delivery_id, delivery_data)
        if not delivery:
            raise HTTPException(status_code=404, detail="Delivery not found")
        
        # TODO: Send status update notification
        # if delivery_data.status:
        #     background_tasks.add_task(send_status_update, delivery_id, delivery_data.status)
        
        return APIResponse(
            success=True,
            message="Delivery updated successfully",
            data={"delivery_id": delivery_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update delivery")


@router.post("/{delivery_id}/assign", response_model=APIResponse)
async def assign_delivery(
    delivery_id: str,
    assignment: DeliveryAssignment,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign delivery to driver."""
    try:
        success = await delivery_service.assign_delivery(db, assignment)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to assign delivery")
        
        # TODO: Send assignment notification to driver
        # background_tasks.add_task(send_assignment_notification, assignment.driver_id, delivery_id)
        
        return APIResponse(
            success=True,
            message="Delivery assigned successfully",
            data={"delivery_id": delivery_id, "driver_id": assignment.driver_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to assign delivery")


@router.post("/{delivery_id}/tracking", response_model=APIResponse)
async def add_tracking_update(
    delivery_id: str,
    tracking_data: TrackingUpdate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add tracking update for delivery."""
    try:
        success = await delivery_service.add_tracking_update(
            db, delivery_id, tracking_data, current_user["user_id"]
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add tracking update")
        
        # TODO: Send real-time update via WebSocket
        # background_tasks.add_task(send_realtime_update, delivery_id, tracking_data)
        
        return APIResponse(
            success=True,
            message="Tracking update added successfully",
            data={"delivery_id": delivery_id}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to add tracking update")


@router.get("/{delivery_id}/tracking", response_model=List[TrackingResponse])
async def get_delivery_tracking(
    delivery_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get tracking history for delivery."""
    try:
        tracking_updates = await delivery_service.get_delivery_tracking(db, delivery_id)
        return [TrackingResponse.from_orm(update) for update in tracking_updates]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch tracking history")


@router.post("/calculate-eta", response_model=ETAResponse)
async def calculate_eta(
    eta_request: ETARequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Calculate ETA for delivery."""
    try:
        eta_data = await delivery_service.calculate_eta(
            eta_request.pickup_lat,
            eta_request.pickup_lng,
            eta_request.delivery_lat,
            eta_request.delivery_lng,
            eta_request.priority.value
        )
        
        return ETAResponse(**eta_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to calculate ETA")


@router.post("/{delivery_id}/auto-assign", response_model=APIResponse)
async def auto_assign_delivery(
    delivery_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Auto-assign delivery to best available driver."""
    try:
        delivery = await delivery_service.get_delivery(db, delivery_id)
        if not delivery:
            raise HTTPException(status_code=404, detail="Delivery not found")
        
        if delivery.status.value != "PENDING":
            raise HTTPException(status_code=400, detail="Delivery is not available for assignment")
        
        # Find best driver
        best_driver = await driver_service.find_best_driver(
            db, delivery.pickup_lat, delivery.pickup_lng,
            delivery.cylinder_size.value, delivery.quantity
        )
        
        if not best_driver:
            raise HTTPException(status_code=404, detail="No available drivers found")
        
        # Calculate ETA
        eta_data = await delivery_service.calculate_eta(
            delivery.pickup_lat, delivery.pickup_lng,
            delivery.delivery_lat, delivery.delivery_lng,
            delivery.priority.value
        )
        
        # Create assignment
        assignment = DeliveryAssignment(
            delivery_id=delivery_id,
            driver_id=str(best_driver.id),
            estimated_pickup_time=eta_data["estimated_pickup_time"],
            estimated_delivery_time=eta_data["estimated_delivery_time"]
        )
        
        success = await delivery_service.assign_delivery(db, assignment)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to assign delivery")
        
        # TODO: Send assignment notification
        # background_tasks.add_task(send_assignment_notification, str(best_driver.id), delivery_id)
        
        return APIResponse(
            success=True,
            message="Delivery auto-assigned successfully",
            data={
                "delivery_id": delivery_id,
                "driver_id": str(best_driver.id),
                "estimated_pickup_time": eta_data["estimated_pickup_time"].isoformat(),
                "estimated_delivery_time": eta_data["estimated_delivery_time"].isoformat()
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to auto-assign delivery")
