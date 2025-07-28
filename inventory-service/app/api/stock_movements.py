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
from app.schemas.inventory import (
    StockMovementCreate, StockMovementResponse, StockMovementFilters,
    PaginatedStockMovementResponse
)
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_user

router = APIRouter()
inventory_service = InventoryService()


# Using shared authentication function from shared.security.auth


@router.post("/", response_model=APIResponse)
async def create_stock_movement(
    movement_data: StockMovementCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create stock movement record."""
    try:
        movement = await inventory_service.create_stock_movement(
            db, movement_data, current_user["user_id"]
        )
        
        # Broadcast stock movement
        background_tasks.add_task(
            websocket_service.broadcast_stock_movement,
            {
                "movement_id": str(movement.id),
                "inventory_id": str(movement.inventory_id),
                "movement_type": movement.movement_type,
                "quantity": movement.quantity,
                "reference_id": movement.reference_id,
                "notes": movement.notes
            }
        )
        
        return APIResponse(
            success=True,
            message="Stock movement recorded successfully",
            data={"movement_id": str(movement.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create stock movement")


@router.get("/", response_model=PaginatedStockMovementResponse)
async def get_stock_movements(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    inventory_id: Optional[str] = Query(None),
    movement_type: Optional[str] = Query(None),
    reference_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get stock movements with filtering and pagination."""
    try:
        filters = StockMovementFilters(
            inventory_id=inventory_id,
            movement_type=movement_type,
            reference_id=reference_id
        )
        
        movements, total = await inventory_service.get_stock_movements(
            db, filters, page, size, current_user["user_id"], current_user["role"]
        )
        
        pages = (total + size - 1) // size
        
        return PaginatedStockMovementResponse(
            items=[StockMovementResponse.from_orm(movement) for movement in movements],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch stock movements")


@router.get("/{movement_id}", response_model=StockMovementResponse)
async def get_stock_movement(
    movement_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific stock movement."""
    try:
        movement = await inventory_service.get_stock_movement_by_id(db, movement_id)
        if not movement:
            raise HTTPException(status_code=404, detail="Stock movement not found")
        
        # Check permissions - vendors can only see their own movements
        if (current_user["role"] == UserRole.VENDOR and 
            str(movement.inventory.vendor_id) != current_user["user_id"]):
            raise HTTPException(status_code=403, detail="Access denied")
        
        return StockMovementResponse.from_orm(movement)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch stock movement")


@router.get("/inventory/{inventory_id}/history")
async def get_inventory_movement_history(
    inventory_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get movement history for specific inventory item."""
    try:
        # Check if inventory exists and user has access
        inventory = await inventory_service.get_inventory_by_id(db, inventory_id)
        if not inventory:
            raise HTTPException(status_code=404, detail="Inventory not found")
        
        if (current_user["role"] == UserRole.VENDOR and 
            str(inventory.vendor_id) != current_user["user_id"]):
            raise HTTPException(status_code=403, detail="Access denied")
        
        filters = StockMovementFilters(inventory_id=inventory_id)
        movements, total = await inventory_service.get_stock_movements(
            db, filters, page, size, current_user["user_id"], current_user["role"]
        )
        
        pages = (total + size - 1) // size
        
        return {
            "inventory_id": inventory_id,
            "movements": [
                {
                    "id": str(movement.id),
                    "movement_type": movement.movement_type,
                    "quantity": movement.quantity,
                    "reference_id": movement.reference_id,
                    "notes": movement.notes,
                    "created_at": movement.created_at.isoformat(),
                    "created_by": str(movement.created_by) if movement.created_by else None
                }
                for movement in movements
            ],
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
                "pages": pages
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch movement history")


@router.get("/analytics/summary")
async def get_movement_analytics(
    vendor_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get stock movement analytics."""
    try:
        # Vendors can only see their own analytics
        if current_user["role"] == UserRole.VENDOR:
            vendor_id = current_user["user_id"]
        
        analytics = await inventory_service.get_movement_analytics(db, vendor_id, days)
        
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch movement analytics")


@router.get("/reports/stock-flow")
async def get_stock_flow_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    inventory_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get stock flow report for analysis."""
    try:
        from datetime import datetime
        
        # Parse dates
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
        
        report = await inventory_service.get_stock_flow_report(
            db, start_dt, end_dt, inventory_id, current_user["user_id"], current_user["role"]
        )
        
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate stock flow report")


@router.post("/bulk-movements", response_model=APIResponse)
async def create_bulk_movements(
    movements: List[StockMovementCreate],
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create multiple stock movements in bulk."""
    try:
        if current_user["role"] not in [UserRole.VENDOR, UserRole.ADMIN]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        results = await inventory_service.create_bulk_movements(
            db, movements, current_user["user_id"]
        )
        
        # Broadcast successful movements
        if results["successful"]:
            for movement_data in results["successful"]:
                background_tasks.add_task(
                    websocket_service.broadcast_stock_movement,
                    movement_data
                )
        
        return APIResponse(
            success=True,
            message=f"Bulk movements completed: {results['success_count']} successful, {results['failure_count']} failed",
            data=results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create bulk movements")
