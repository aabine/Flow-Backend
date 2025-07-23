from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import CylinderSize


# Inventory Location Schemas
class InventoryCreate(BaseModel):
    location_name: str
    address: str
    city: str
    state: str
    country: str = "Nigeria"
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class InventoryUpdate(BaseModel):
    location_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None


class InventoryResponse(BaseModel):
    id: str
    vendor_id: str
    location_name: str
    address: str
    city: str
    state: str
    country: str
    latitude: float
    longitude: float
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Stock Schemas
class StockCreate(BaseModel):
    cylinder_size: CylinderSize
    total_quantity: int = Field(..., ge=0)
    minimum_threshold: int = Field(5, ge=0)


class StockUpdate(BaseModel):
    total_quantity: Optional[int] = Field(None, ge=0)
    minimum_threshold: Optional[int] = Field(None, ge=0)


class StockResponse(BaseModel):
    id: str
    inventory_id: str
    cylinder_size: CylinderSize
    total_quantity: int
    available_quantity: int
    reserved_quantity: int
    minimum_threshold: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Stock Movement Schemas
class StockMovementCreate(BaseModel):
    cylinder_size: CylinderSize
    movement_type: str  # 'in', 'out', 'reserved', 'released'
    quantity: int = Field(..., gt=0)
    order_id: Optional[str] = None
    notes: Optional[str] = None


class StockMovementResponse(BaseModel):
    id: str
    inventory_id: str
    stock_id: str
    cylinder_size: CylinderSize
    movement_type: str
    quantity: int
    previous_quantity: int
    new_quantity: int
    order_id: Optional[str] = None
    notes: Optional[str] = None
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# Vendor Inventory Response
class VendorInventoryResponse(BaseModel):
    inventory_locations: List[InventoryResponse]
    total_locations: int
    total_stock: dict  # {cylinder_size: total_quantity}
    low_stock_alerts: List[dict]

    class Config:
        from_attributes = True


# Search and Availability Schemas
class InventorySearchResult(BaseModel):
    inventory_id: str
    vendor_id: str
    location_name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    distance_km: float
    available_quantity: int
    vendor_rating: Optional[float] = None

    class Config:
        from_attributes = True


class StockReservationCreate(BaseModel):
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)
    order_id: str


class StockReservationResponse(BaseModel):
    id: str
    inventory_id: str
    stock_id: str
    order_id: str
    cylinder_size: CylinderSize
    quantity: int
    reserved_by: str
    expires_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
