from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.inventory_service import InventoryService
from app.services.websocket_service import websocket_service
from app.services.event_service import event_service
from app.schemas.inventory import (
    InventoryCreate, InventoryUpdate, InventoryResponse,
    StockCreate, StockUpdate, StockResponse,
    StockMovementCreate, StockMovementResponse,
    StockReservationCreate, StockReservationResponse,
    VendorInventoryResponse, InventorySearchResult,
    InventoryLocationCreate, InventoryLocationResponse,
    InventoryFilters, PaginatedInventoryResponse,
    StockAdjustment, BulkStockUpdate
)
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_user

router = APIRouter()
inventory_service = InventoryService()


# Using shared authentication function from shared.security.auth


@router.post("/", response_model=APIResponse)
async def create_inventory(
    inventory_data: InventoryCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new inventory item."""
    try:
        # Only vendors can create inventory
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can create inventory")
        
        inventory = await inventory_service.create_inventory(
            db, inventory_data, current_user["user_id"]
        )
        
        # Broadcast inventory creation
        background_tasks.add_task(
            websocket_service.broadcast_stock_update,
            {
                "inventory_id": str(inventory.id),
                "vendor_id": str(inventory.vendor_id),
                "location_id": str(inventory.location_id),
                "cylinder_size": inventory.cylinder_size,
                "available_quantity": inventory.available_quantity,
                "total_quantity": inventory.total_quantity,
                "low_stock_threshold": inventory.low_stock_threshold
            }
        )
        
        # Publish event
        background_tasks.add_task(
            event_service.emit_inventory_created,
            {
                "inventory_id": str(inventory.id),
                "vendor_id": str(inventory.vendor_id),
                "cylinder_size": inventory.cylinder_size,
                "quantity": inventory.total_quantity
            }
        )
        
        return APIResponse(
            success=True,
            message="Inventory created successfully",
            data={"inventory_id": str(inventory.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=PaginatedInventoryResponse)
async def get_inventory(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    vendor_id: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    cylinder_size: Optional[str] = Query(None),
    low_stock_only: Optional[bool] = Query(False),
    available_only: Optional[bool] = Query(False),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get inventory with filtering and pagination."""
    try:
        filters = InventoryFilters(
            vendor_id=vendor_id,
            location_id=location_id,
            cylinder_size=cylinder_size,
            low_stock_only=low_stock_only,
            available_only=available_only
        )
        
        # Vendors can only see their own inventory
        if current_user["role"] == UserRole.VENDOR:
            filters.vendor_id = current_user["user_id"]
        
        inventory_items, total = await inventory_service.get_inventory(
            db, filters, page, size
        )
        
        pages = (total + size - 1) // size
        
        return PaginatedInventoryResponse(
            items=[InventoryResponse.from_orm(item) for item in inventory_items],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch inventory")


@router.get("/{inventory_id}", response_model=InventoryResponse)
async def get_inventory_item(
    inventory_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific inventory item."""
    try:
        inventory = await inventory_service.get_inventory_by_id(db, inventory_id)
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")
        
        # Check permissions
        if (current_user["role"] == UserRole.VENDOR and 
            str(inventory.vendor_id) != current_user["user_id"]):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return InventoryResponse.from_orm(inventory)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch inventory item")


@router.put("/{inventory_id}", response_model=APIResponse)
async def update_inventory(
    inventory_id: str,
    inventory_data: InventoryUpdate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update inventory item."""
    try:
        inventory = await inventory_service.update_inventory(
            db, inventory_id, inventory_data, current_user["user_id"]
        )
        
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")
        
        # Broadcast update
        background_tasks.add_task(
            websocket_service.broadcast_stock_update,
            {
                "inventory_id": str(inventory.id),
                "vendor_id": str(inventory.vendor_id),
                "location_id": str(inventory.location_id),
                "cylinder_size": inventory.cylinder_size,
                "available_quantity": inventory.available_quantity,
                "total_quantity": inventory.total_quantity,
                "low_stock_threshold": inventory.low_stock_threshold,
                "is_low_stock": inventory.available_quantity <= inventory.low_stock_threshold
            }
        )
        
        return APIResponse(
            success=True,
            message="Inventory updated successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update inventory")


@router.post("/{inventory_id}/adjust-stock", response_model=APIResponse)
async def adjust_stock(
    inventory_id: str,
    adjustment: StockAdjustment,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Adjust stock levels (add or remove stock)."""
    try:
        inventory = await inventory_service.adjust_stock(
            db, inventory_id, adjustment, current_user["user_id"]
        )
        
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")
        
        # Broadcast stock update
        background_tasks.add_task(
            websocket_service.broadcast_stock_update,
            {
                "inventory_id": str(inventory.id),
                "vendor_id": str(inventory.vendor_id),
                "location_id": str(inventory.location_id),
                "cylinder_size": inventory.cylinder_size,
                "available_quantity": inventory.available_quantity,
                "total_quantity": inventory.total_quantity,
                "is_low_stock": inventory.available_quantity <= inventory.low_stock_threshold
            }
        )
        
        # Check for low stock alert
        if inventory.available_quantity <= inventory.low_stock_threshold:
            background_tasks.add_task(
                websocket_service.broadcast_low_stock_alert,
                {
                    "inventory_id": str(inventory.id),
                    "vendor_id": str(inventory.vendor_id),
                    "cylinder_size": inventory.cylinder_size,
                    "available_quantity": inventory.available_quantity,
                    "low_stock_threshold": inventory.low_stock_threshold
                }
            )
        
        return APIResponse(
            success=True,
            message=f"Stock {adjustment.adjustment_type}ed successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to adjust stock")


@router.post("/bulk-update", response_model=APIResponse)
async def bulk_update_stock(
    bulk_update: BulkStockUpdate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Bulk update multiple inventory items."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can bulk update inventory")
        
        results = await inventory_service.bulk_update_inventory(
            db, bulk_update, current_user["user_id"]
        )
        
        # Broadcast bulk updates
        if results["successful"]:
            background_tasks.add_task(
                websocket_service.broadcast_bulk_stock_update,
                results["successful"]
            )
        
        return APIResponse(
            success=True,
            message=f"Bulk update completed: {results['success_count']} successful, {results['failure_count']} failed",
            data=results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to perform bulk update")


@router.get("/low-stock/alerts")
async def get_low_stock_alerts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get low stock alerts for vendor."""
    try:
        vendor_id = current_user["user_id"] if current_user["role"] == UserRole.VENDOR else None
        
        low_stock_items = await inventory_service.get_low_stock_items(db, vendor_id)
        
        return {
            "low_stock_items": [
                {
                    "inventory_id": str(item.id),
                    "cylinder_size": item.cylinder_size,
                    "available_quantity": item.available_quantity,
                    "threshold": item.low_stock_threshold,
                    "location_name": item.location.name if item.location else None
                }
                for item in low_stock_items
            ],
            "total_alerts": len(low_stock_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch low stock alerts")


# Reservation Management Routes
@router.post("/reservations", response_model=APIResponse)
async def create_reservation(
    reservation_data: StockReservationCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create inventory reservation for order."""
    try:
        reservation = await inventory_service.create_reservation(
            db, reservation_data, current_user["user_id"]
        )

        # Broadcast reservation update
        background_tasks.add_task(
            websocket_service.broadcast_reservation_update,
            {
                "reservation_id": str(reservation.id),
                "inventory_id": str(reservation.inventory_id),
                "order_id": str(reservation.order_id),
                "quantity": reservation.quantity,
                "status": reservation.status,
                "expires_at": reservation.expires_at.isoformat() if reservation.expires_at else None
            }
        )

        return APIResponse(
            success=True,
            message="Reservation created successfully",
            data={"reservation_id": str(reservation.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create reservation")


@router.get("/reservations/{reservation_id}", response_model=StockReservationResponse)
async def get_reservation(
    reservation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific reservation."""
    try:
        reservation = await inventory_service.get_reservation(db, reservation_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        return StockReservationResponse.from_orm(reservation)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch reservation")


@router.post("/reservations/{reservation_id}/confirm", response_model=APIResponse)
async def confirm_reservation(
    reservation_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm reservation and deduct stock."""
    try:
        reservation = await inventory_service.confirm_reservation(
            db, reservation_id, current_user["user_id"]
        )

        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Broadcast confirmation
        background_tasks.add_task(
            websocket_service.broadcast_reservation_update,
            {
                "reservation_id": str(reservation.id),
                "inventory_id": str(reservation.inventory_id),
                "order_id": str(reservation.order_id),
                "quantity": reservation.quantity,
                "status": reservation.status
            }
        )

        return APIResponse(
            success=True,
            message="Reservation confirmed successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to confirm reservation")


@router.delete("/reservations/{reservation_id}", response_model=APIResponse)
async def cancel_reservation(
    reservation_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel reservation and release stock."""
    try:
        success = await inventory_service.cancel_reservation(
            db, reservation_id, current_user["user_id"]
        )

        if not success:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # Broadcast cancellation
        background_tasks.add_task(
            websocket_service.broadcast_reservation_update,
            {
                "reservation_id": reservation_id,
                "status": "cancelled"
            }
        )

        return APIResponse(
            success=True,
            message="Reservation cancelled successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to cancel reservation")


# Location Management Routes
@router.post("/locations", response_model=APIResponse)
async def create_inventory_location(
    location_data: InventoryLocationCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new inventory location."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can create locations")

        location = await inventory_service.create_inventory_location(
            db, location_data, current_user["user_id"]
        )

        return APIResponse(
            success=True,
            message="Inventory location created successfully",
            data={"location_id": str(location.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create location")


@router.get("/locations", response_model=List[InventoryLocationResponse])
async def get_inventory_locations(
    vendor_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get inventory locations."""
    try:
        # Vendors can only see their own locations
        if current_user["role"] == UserRole.VENDOR:
            vendor_id = current_user["user_id"]

        locations = await inventory_service.get_inventory_locations(db, vendor_id)

        return [InventoryLocationResponse.from_orm(location) for location in locations]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch locations")


# Analytics and Monitoring Routes
@router.get("/analytics/summary")
async def get_inventory_summary(
    vendor_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get inventory analytics summary."""
    try:
        # Vendors can only see their own analytics
        if current_user["role"] == UserRole.VENDOR:
            vendor_id = current_user["user_id"]

        summary = await inventory_service.get_inventory_analytics(db, vendor_id)

        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch inventory analytics")


@router.get("/real-time/summary")
async def get_real_time_summary(
    current_user: dict = Depends(get_current_user)
):
    """Get real-time inventory summary."""
    try:
        vendor_id = current_user["user_id"] if current_user["role"] == UserRole.VENDOR else None

        summary = await websocket_service.get_real_time_inventory_summary(vendor_id)

        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch real-time summary")
