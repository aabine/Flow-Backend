from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import sys
import os
import uuid

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import OrderStatus, CylinderSize, PaginatedResponse


class OrderItemCreate(BaseModel):
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)


class OrderItemResponse(BaseModel):
    id: str
    cylinder_size: CylinderSize
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None

    @validator('id', pre=True)
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    delivery_address: str
    delivery_latitude: float = Field(..., ge=-90, le=90)
    delivery_longitude: float = Field(..., ge=-180, le=180)
    delivery_contact_name: Optional[str] = None
    delivery_contact_phone: Optional[str] = None
    is_emergency: bool = False
    notes: Optional[str] = None
    special_instructions: Optional[str] = None
    requested_delivery_time: Optional[datetime] = None
    preferred_vendor_id: Optional[str] = None
    auto_assign_vendor: bool = True  # Automatically find best vendor
    max_distance_km: float = Field(50.0, gt=0)  # Maximum distance for vendor search


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    vendor_id: Optional[str] = None
    notes: Optional[str] = None
    delivery_notes: Optional[str] = None
    estimated_delivery_time: Optional[datetime] = None
    actual_delivery_time: Optional[datetime] = None
    tracking_number: Optional[str] = None


class OrderStatusHistoryResponse(BaseModel):
    id: str
    status: OrderStatus
    notes: Optional[str] = None
    updated_by: str
    created_at: datetime

    @validator('id', 'updated_by', pre=True)
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    reference: str
    hospital_id: str
    vendor_id: Optional[str] = None
    status: OrderStatus
    is_emergency: bool
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    delivery_contact_name: Optional[str] = None
    delivery_contact_phone: Optional[str] = None
    notes: Optional[str] = None
    special_instructions: Optional[str] = None
    subtotal: Optional[float] = None
    delivery_fee: Optional[float] = None
    emergency_surcharge: Optional[float] = None
    total_amount: Optional[float] = None
    requested_delivery_time: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    actual_delivery_time: Optional[datetime] = None
    tracking_number: Optional[str] = None
    delivery_notes: Optional[str] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[OrderItemResponse] = []
    status_history: List[OrderStatusHistoryResponse] = []

    @validator('id', 'hospital_id', 'vendor_id', pre=True)
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True


class OrderListResponse(PaginatedResponse):
    items: List[OrderResponse]


class OrderTrackingResponse(BaseModel):
    order_id: str
    reference: str
    status: OrderStatus
    estimated_delivery_time: Optional[datetime] = None
    tracking_number: Optional[str] = None
    delivery_progress: List[OrderStatusHistoryResponse] = []
    current_location: Optional[dict] = None
    eta_minutes: Optional[int] = None


class OrderStatsResponse(BaseModel):
    total_orders: int
    pending_orders: int
    confirmed_orders: int
    in_transit_orders: int
    delivered_orders: int
    cancelled_orders: int
    emergency_orders: int
    total_revenue: float
    average_order_value: float


# Direct Ordering Schemas
class DirectOrderCreate(BaseModel):
    """Direct order creation with automatic vendor selection."""
    items: List[OrderItemCreate]
    delivery_address: str
    delivery_latitude: float = Field(..., ge=-90, le=90)
    delivery_longitude: float = Field(..., ge=-180, le=180)
    delivery_contact_name: Optional[str] = None
    delivery_contact_phone: Optional[str] = None
    is_emergency: bool = False
    notes: Optional[str] = None
    special_instructions: Optional[str] = None
    requested_delivery_time: Optional[datetime] = None
    max_distance_km: float = Field(50.0, gt=0)
    vendor_selection_criteria: str = Field("best_price", pattern="^(best_price|fastest_delivery|closest_distance|highest_rating)$")


class VendorSelectionResult(BaseModel):
    """Result of vendor selection process."""
    vendor_id: str
    vendor_name: str
    location_id: str
    location_name: str
    distance_km: float
    estimated_delivery_time_hours: int
    total_price: float
    selection_reason: str
    vendor_rating: Optional[float] = None


class DirectOrderResponse(BaseModel):
    """Response for direct order creation."""
    order: OrderResponse
    vendor_selection: VendorSelectionResult
    pricing_breakdown: dict
    estimated_total: float


class OrderPricingRequest(BaseModel):
    """Request for order pricing calculation."""
    items: List[OrderItemCreate]
    delivery_latitude: float = Field(..., ge=-90, le=90)
    delivery_longitude: float = Field(..., ge=-180, le=180)
    is_emergency: bool = False
    vendor_id: Optional[str] = None  # If specific vendor requested
    max_distance_km: float = Field(50.0, gt=0)


class OrderPricingResponse(BaseModel):
    """Response for order pricing calculation."""
    vendor_options: List[VendorSelectionResult]
    recommended_vendor: VendorSelectionResult
    pricing_breakdown: dict
