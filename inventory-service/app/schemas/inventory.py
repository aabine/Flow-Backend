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
    vendor_name: str
    location_name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    distance_km: float
    available_quantity: int
    unit_price: Optional[float] = None
    delivery_fee: Optional[float] = None
    emergency_surcharge: Optional[float] = None
    minimum_order_quantity: Optional[int] = 1
    maximum_order_quantity: Optional[int] = None
    estimated_delivery_time_hours: Optional[int] = None
    vendor_rating: Optional[float] = None
    is_available: bool = True

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


# Additional schemas for API compatibility
class InventoryLocationCreate(BaseModel):
    name: str
    address: str
    city: str
    state: str
    country: str = "Nigeria"
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class InventoryLocationResponse(BaseModel):
    id: str
    name: str
    address: str
    city: str
    state: str
    country: str
    latitude: float
    longitude: float
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryFilters(BaseModel):
    vendor_id: Optional[str] = None
    location_id: Optional[str] = None
    cylinder_size: Optional[CylinderSize] = None
    low_stock_only: Optional[bool] = False
    available_only: Optional[bool] = False


class PaginatedInventoryResponse(BaseModel):
    items: List[InventoryResponse]
    total: int
    page: int
    size: int
    pages: int


class StockAdjustment(BaseModel):
    cylinder_size: CylinderSize
    adjustment_type: str  # 'add' or 'remove'
    quantity: int = Field(..., gt=0)
    reason: Optional[str] = None


class BulkStockUpdate(BaseModel):
    updates: List[dict]  # List of stock updates
    reason: Optional[str] = None


class StockMovementFilters(BaseModel):
    inventory_id: Optional[str] = None
    movement_type: Optional[str] = None
    cylinder_size: Optional[CylinderSize] = None
    order_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class PaginatedStockMovementResponse(BaseModel):
    items: List[StockMovementResponse]
    total: int
    page: int
    size: int
    pages: int


# Product Catalog Integration Schemas
class ProductCatalogRequest(BaseModel):
    hospital_latitude: float = Field(..., ge=-90, le=90)
    hospital_longitude: float = Field(..., ge=-180, le=180)
    cylinder_size: Optional[CylinderSize] = None
    quantity: int = Field(1, gt=0)
    max_distance_km: float = Field(50.0, gt=0)
    is_emergency: bool = False
    sort_by: str = Field("distance", regex="^(distance|price|rating|delivery_time)$")
    sort_order: str = Field("asc", regex="^(asc|desc)$")


class ProductCatalogItem(BaseModel):
    vendor_id: str
    vendor_name: str
    location_id: str
    location_name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    distance_km: float
    cylinder_size: CylinderSize
    available_quantity: int
    unit_price: float
    delivery_fee: float
    emergency_surcharge: float
    minimum_order_quantity: int
    maximum_order_quantity: Optional[int]
    estimated_delivery_time_hours: int
    vendor_rating: Optional[float] = None
    is_available: bool = True

    class Config:
        from_attributes = True


class ProductCatalogResponse(BaseModel):
    items: List[ProductCatalogItem]
    total: int
    search_radius_km: float
    hospital_location: dict
    filters_applied: ProductCatalogRequest


# Real-time Availability Schemas
class AvailabilityCheck(BaseModel):
    vendor_id: str
    location_id: str
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)


class AvailabilityResponse(BaseModel):
    vendor_id: str
    location_id: str
    cylinder_size: CylinderSize
    available_quantity: int
    is_available: bool
    unit_price: Optional[float] = None
    delivery_fee: Optional[float] = None
    estimated_delivery_time_hours: Optional[int] = None
    last_updated: datetime

    class Config:
        from_attributes = True


class BulkAvailabilityCheck(BaseModel):
    checks: List[AvailabilityCheck]


class BulkAvailabilityResponse(BaseModel):
    results: List[AvailabilityResponse]
    total_checked: int
    available_count: int
    unavailable_count: int
