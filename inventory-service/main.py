from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import get_db
from app.models.inventory import Inventory, CylinderStock, StockMovement
from app.schemas.inventory import (
    InventoryCreate, InventoryResponse, InventoryUpdate, 
    StockMovementResponse, VendorInventoryResponse
)
from app.services.inventory_service import InventoryService
from app.services.event_service import EventService
from shared.models import CylinderSize, UserRole, APIResponse

app = FastAPI(
    title="Inventory Service",
    description="Oxygen cylinder inventory management service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

inventory_service = InventoryService()
event_service = EventService()


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
        "service": "Inventory Service",
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


@app.post("/inventory", response_model=APIResponse)
async def create_inventory_location(
    inventory_data: InventoryCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create inventory location (vendor only)."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create inventory locations"
            )
        
        inventory = await inventory_service.create_inventory_location(
            db, current_user["user_id"], inventory_data
        )
        
        return APIResponse(
            success=True,
            message="Inventory location created successfully",
            data={
                "inventory_id": str(inventory.id),
                "location_name": inventory.location_name
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create inventory location: {str(e)}"
        )


@app.get("/inventory", response_model=List[InventoryResponse])
async def get_vendor_inventory(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor's inventory locations."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can access inventory"
            )
        
        inventory_locations = await inventory_service.get_vendor_inventory(
            db, current_user["user_id"]
        )
        
        return [InventoryResponse.from_orm(inv) for inv in inventory_locations]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get inventory: {str(e)}"
        )


@app.put("/inventory/{inventory_id}/stock", response_model=APIResponse)
async def update_stock(
    inventory_id: str,
    cylinder_size: CylinderSize,
    quantity_change: int,
    notes: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update cylinder stock."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can update stock"
            )
        
        # Verify inventory belongs to vendor
        inventory = await inventory_service.get_inventory_by_id(db, inventory_id)
        if not inventory or str(inventory.vendor_id) != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory location not found"
            )
        
        # Update stock
        stock = await inventory_service.update_stock(
            db, inventory_id, cylinder_size, quantity_change, current_user["user_id"], notes
        )
        
        # Emit inventory updated event
        await event_service.emit_inventory_updated(inventory, cylinder_size, stock.available_quantity)
        
        return APIResponse(
            success=True,
            message="Stock updated successfully",
            data={
                "inventory_id": inventory_id,
                "cylinder_size": cylinder_size,
                "new_quantity": stock.available_quantity
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update stock: {str(e)}"
        )


@app.get("/inventory/{inventory_id}/stock")
async def get_inventory_stock(
    inventory_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get stock levels for inventory location."""
    try:
        inventory = await inventory_service.get_inventory_by_id(db, inventory_id)
        if not inventory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory location not found"
            )
        
        # Check access permissions
        if (current_user["role"] == UserRole.VENDOR and 
            str(inventory.vendor_id) != current_user["user_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        stock_levels = await inventory_service.get_stock_levels(db, inventory_id)
        
        return {
            "inventory_id": inventory_id,
            "location_name": inventory.location_name,
            "stock_levels": [
                {
                    "cylinder_size": stock.cylinder_size,
                    "available_quantity": stock.available_quantity,
                    "reserved_quantity": stock.reserved_quantity,
                    "total_quantity": stock.total_quantity,
                    "last_updated": stock.updated_at
                }
                for stock in stock_levels
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock levels: {str(e)}"
        )


@app.get("/inventory/search")
async def search_available_inventory(
    cylinder_size: CylinderSize,
    quantity: int,
    latitude: float,
    longitude: float,
    max_distance_km: float = 50.0,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search for available inventory near location."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can search inventory"
            )
        
        available_inventory = await inventory_service.search_available_inventory(
            db, cylinder_size, quantity, latitude, longitude, max_distance_km
        )
        
        return {
            "search_criteria": {
                "cylinder_size": cylinder_size,
                "quantity": quantity,
                "location": {"latitude": latitude, "longitude": longitude},
                "max_distance_km": max_distance_km
            },
            "results": [
                {
                    "vendor_id": str(inv.vendor_id),
                    "inventory_id": str(inv.id),
                    "location_name": inv.location_name,
                    "available_quantity": inv.available_quantity,
                    "distance_km": inv.distance_km,
                    "estimated_delivery_time": inv.estimated_delivery_time
                }
                for inv in available_inventory
            ],
            "total_results": len(available_inventory)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search inventory: {str(e)}"
        )


@app.post("/inventory/{inventory_id}/reserve", response_model=APIResponse)
async def reserve_stock(
    inventory_id: str,
    cylinder_size: CylinderSize,
    quantity: int,
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reserve stock for an order."""
    try:
        # This endpoint is typically called by the order service
        reservation = await inventory_service.reserve_stock(
            db, inventory_id, cylinder_size, quantity, order_id
        )
        
        return APIResponse(
            success=True,
            message="Stock reserved successfully",
            data={
                "reservation_id": str(reservation.id),
                "inventory_id": inventory_id,
                "quantity_reserved": quantity
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reserve stock: {str(e)}"
        )


@app.post("/inventory/{inventory_id}/release", response_model=APIResponse)
async def release_reservation(
    inventory_id: str,
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Release stock reservation."""
    try:
        await inventory_service.release_reservation(db, inventory_id, order_id)
        
        return APIResponse(
            success=True,
            message="Stock reservation released successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release reservation: {str(e)}"
        )


@app.get("/inventory/{inventory_id}/movements")
async def get_stock_movements(
    inventory_id: str,
    page: int = 1,
    size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get stock movement history."""
    try:
        inventory = await inventory_service.get_inventory_by_id(db, inventory_id)
        if not inventory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory location not found"
            )
        
        # Check access permissions
        if (current_user["role"] == UserRole.VENDOR and 
            str(inventory.vendor_id) != current_user["user_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        movements, total = await inventory_service.get_stock_movements(
            db, inventory_id, page, size
        )
        
        return {
            "movements": [StockMovementResponse.from_orm(movement) for movement in movements],
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock movements: {str(e)}"
        )


@app.get("/vendors/{vendor_id}/availability")
async def check_vendor_availability(
    vendor_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Check if vendor has available inventory (internal service call)."""
    try:
        is_available = await inventory_service.check_vendor_availability(db, vendor_id)
        
        return {
            "vendor_id": vendor_id,
            "available": is_available,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check availability: {str(e)}"
        )


@app.get("/low-stock-alerts")
async def get_low_stock_alerts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get low stock alerts for vendor."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can access stock alerts"
            )
        
        alerts = await inventory_service.get_low_stock_alerts(db, current_user["user_id"])
        
        return {
            "alerts": alerts,
            "count": len(alerts)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock alerts: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
