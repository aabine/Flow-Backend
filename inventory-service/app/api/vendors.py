"""
Vendor API endpoints for inventory service
Handles vendor-specific operations like availability checking
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.inventory_service import InventoryService
from app.services.cache_service import cache_service
from app.models.inventory import Inventory, CylinderStock
from shared.models import APIResponse, UserRole, CylinderSize
from shared.security.auth import get_current_user

router = APIRouter()
inventory_service = InventoryService()


class VendorAvailabilityResponse:
    """Response model for vendor availability"""
    def __init__(self, available: bool, last_updated: datetime, capacity_info: Dict[str, Any]):
        self.available = available
        self.last_updated = last_updated
        self.capacity_info = capacity_info
    
    def dict(self):
        return {
            "available": self.available,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "capacity_info": self.capacity_info
        }


@router.get("/{vendor_id}/availability")
async def get_vendor_availability(
    vendor_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    use_cache: bool = True
):
    """
    Get vendor availability status and capacity information.

    Returns vendor availability status including:
    - Overall availability (boolean)
    - Last updated timestamp
    - Capacity information by cylinder size
    - Total inventory locations
    - Active stock levels

    Uses Redis caching for improved performance.
    """
    # Check cache first if enabled
    if use_cache:
        cached_data = await cache_service.get_vendor_availability(vendor_id)
        if cached_data:
            return cached_data

    try:
        # Optimized query: Get inventory locations and stock in a single join query
        result = await db.execute(
            select(Inventory, CylinderStock)
            .outerjoin(CylinderStock, Inventory.id == CylinderStock.inventory_id)
            .where(and_(
                Inventory.vendor_id == vendor_id,
                Inventory.is_active == True
            ))
        )
        inventory_data = result.all()

        if not inventory_data:
            # Vendor has no inventory locations
            return {
                "available": False,
                "last_updated": datetime.utcnow().isoformat(),
                "capacity_info": {
                    "total_locations": 0,
                    "active_locations": 0,
                    "cylinder_stock": {},
                    "total_available_units": 0,
                    "low_stock_alerts": 0
                },
                "message": "Vendor has no active inventory locations"
            }

        # Process the joined data
        inventory_locations = set()
        stock_records = []

        for inventory, stock in inventory_data:
            inventory_locations.add(inventory)
            if stock:
                stock_records.append(stock)
        
        # Calculate capacity information
        capacity_info = {
            "total_locations": len(inventory_locations),
            "active_locations": len(inventory_locations),
            "cylinder_stock": {},
            "total_available_units": 0,
            "low_stock_alerts": 0
        }
        
        # Group stock by cylinder size
        for stock in stock_records:
            size_key = stock.cylinder_size.value if hasattr(stock.cylinder_size, 'value') else str(stock.cylinder_size)
            
            if size_key not in capacity_info["cylinder_stock"]:
                capacity_info["cylinder_stock"][size_key] = {
                    "total_quantity": 0,
                    "available_quantity": 0,
                    "reserved_quantity": 0,
                    "locations_with_stock": 0,
                    "minimum_threshold": 0
                }
            
            stock_info = capacity_info["cylinder_stock"][size_key]
            stock_info["total_quantity"] += stock.total_quantity
            stock_info["available_quantity"] += stock.available_quantity
            stock_info["reserved_quantity"] += stock.reserved_quantity
            stock_info["minimum_threshold"] += stock.minimum_threshold
            
            if stock.total_quantity > 0:
                stock_info["locations_with_stock"] += 1
            
            # Check for low stock
            if stock.available_quantity <= stock.minimum_threshold:
                capacity_info["low_stock_alerts"] += 1
        
        # Calculate total available units across all cylinder sizes
        capacity_info["total_available_units"] = sum(
            stock["available_quantity"] 
            for stock in capacity_info["cylinder_stock"].values()
        )
        
        # Determine overall availability
        # Vendor is available if they have at least some stock available
        is_available = capacity_info["total_available_units"] > 0
        
        # Get the most recent update time from stock records
        last_updated = datetime.utcnow()
        if stock_records:
            latest_update = max(
                (stock.updated_at or stock.created_at for stock in stock_records),
                default=datetime.utcnow()
            )
            last_updated = latest_update
        
        availability_data = {
            "available": is_available,
            "last_updated": last_updated.isoformat(),
            "capacity_info": capacity_info
        }

        # Cache the result for future requests
        if use_cache:
            await cache_service.set_vendor_availability(vendor_id, availability_data)

        return availability_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor availability: {str(e)}"
        )


@router.get("/{vendor_id}/locations")
async def get_vendor_locations(
    vendor_id: str,
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all inventory locations for a vendor."""
    try:
        query = select(Inventory).where(Inventory.vendor_id == vendor_id)
        
        if active_only:
            query = query.where(Inventory.is_active == True)
        
        result = await db.execute(query)
        locations = result.scalars().all()
        
        return {
            "vendor_id": vendor_id,
            "total_locations": len(locations),
            "locations": [
                {
                    "id": str(location.id),
                    "location_name": location.location_name,
                    "address": location.address,
                    "city": location.city,
                    "state": location.state,
                    "country": location.country,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "is_active": location.is_active,
                    "created_at": location.created_at.isoformat() if location.created_at else None
                }
                for location in locations
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor locations: {str(e)}"
        )


@router.get("/{vendor_id}/stock-summary")
async def get_vendor_stock_summary(
    vendor_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a summary of vendor's stock across all locations."""
    try:
        # Get all inventory locations for this vendor
        result = await db.execute(
            select(Inventory)
            .where(and_(
                Inventory.vendor_id == vendor_id,
                Inventory.is_active == True
            ))
        )
        inventory_locations = result.scalars().all()
        
        if not inventory_locations:
            return {
                "vendor_id": vendor_id,
                "total_locations": 0,
                "stock_summary": {},
                "message": "No active inventory locations found"
            }
        
        location_ids = [str(loc.id) for loc in inventory_locations]
        
        # Get aggregated stock data
        result = await db.execute(
            select(
                CylinderStock.cylinder_size,
                func.sum(CylinderStock.total_quantity).label('total_qty'),
                func.sum(CylinderStock.available_quantity).label('available_qty'),
                func.sum(CylinderStock.reserved_quantity).label('reserved_qty'),
                func.count(CylinderStock.id).label('location_count')
            )
            .where(CylinderStock.inventory_id.in_(location_ids))
            .group_by(CylinderStock.cylinder_size)
        )
        
        stock_summary = {}
        for row in result:
            size_key = row.cylinder_size.value if hasattr(row.cylinder_size, 'value') else str(row.cylinder_size)
            stock_summary[size_key] = {
                "total_quantity": int(row.total_qty or 0),
                "available_quantity": int(row.available_qty or 0),
                "reserved_quantity": int(row.reserved_qty or 0),
                "locations_with_stock": int(row.location_count or 0)
            }
        
        return {
            "vendor_id": vendor_id,
            "total_locations": len(inventory_locations),
            "stock_summary": stock_summary,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor stock summary: {str(e)}"
        )
