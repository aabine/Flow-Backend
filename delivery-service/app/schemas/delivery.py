from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import CylinderSize


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeliveryPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class DriverStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFF_DUTY = "OFF_DUTY"
    UNAVAILABLE = "UNAVAILABLE"


class VehicleType(str, Enum):
    MOTORCYCLE = "MOTORCYCLE"
    CAR = "CAR"
    VAN = "VAN"
    TRUCK = "TRUCK"


# Driver Schemas
class DriverCreate(BaseModel):
    user_id: str
    driver_license: str
    phone_number: str
    vehicle_type: VehicleType
    vehicle_plate: str
    vehicle_capacity: int = Field(..., gt=0)


class DriverUpdate(BaseModel):
    phone_number: Optional[str] = None
    vehicle_type: Optional[VehicleType] = None
    vehicle_plate: Optional[str] = None
    vehicle_capacity: Optional[int] = Field(None, gt=0)
    current_location_lat: Optional[float] = Field(None, ge=-90, le=90)
    current_location_lng: Optional[float] = Field(None, ge=-180, le=180)
    status: Optional[DriverStatus] = None
    is_active: Optional[bool] = None


class DriverResponse(BaseModel):
    id: str
    user_id: str
    driver_license: str
    phone_number: str
    vehicle_type: VehicleType
    vehicle_plate: str
    vehicle_capacity: int
    current_location_lat: Optional[float] = None
    current_location_lng: Optional[float] = None
    status: DriverStatus
    rating: float
    total_deliveries: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Delivery Schemas
class DeliveryCreate(BaseModel):
    order_id: str
    customer_id: str
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)
    priority: DeliveryPriority = DeliveryPriority.NORMAL
    pickup_address: str
    pickup_lat: float = Field(..., ge=-90, le=90)
    pickup_lng: float = Field(..., ge=-180, le=180)
    delivery_address: str
    delivery_lat: float = Field(..., ge=-90, le=90)
    delivery_lng: float = Field(..., ge=-180, le=180)
    requested_delivery_time: Optional[datetime] = None
    delivery_fee: float = Field(..., ge=0)
    special_instructions: Optional[str] = None


class DeliveryUpdate(BaseModel):
    driver_id: Optional[str] = None
    status: Optional[DeliveryStatus] = None
    estimated_pickup_time: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    actual_pickup_time: Optional[datetime] = None
    actual_delivery_time: Optional[datetime] = None
    delivery_notes: Optional[str] = None
    customer_signature: Optional[str] = None
    delivery_photo: Optional[str] = None


class DeliveryResponse(BaseModel):
    id: str
    order_id: str
    customer_id: str
    driver_id: Optional[str] = None
    cylinder_size: CylinderSize
    quantity: int
    priority: DeliveryPriority
    status: DeliveryStatus
    pickup_address: str
    pickup_lat: float
    pickup_lng: float
    delivery_address: str
    delivery_lat: float
    delivery_lng: float
    requested_delivery_time: Optional[datetime] = None
    estimated_pickup_time: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    actual_pickup_time: Optional[datetime] = None
    actual_delivery_time: Optional[datetime] = None
    distance_km: Optional[float] = None
    delivery_fee: float
    special_instructions: Optional[str] = None
    delivery_notes: Optional[str] = None
    customer_signature: Optional[str] = None
    delivery_photo: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Tracking Schemas
class TrackingUpdate(BaseModel):
    status: DeliveryStatus
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lng: Optional[float] = Field(None, ge=-180, le=180)
    notes: Optional[str] = None


class TrackingResponse(BaseModel):
    id: str
    delivery_id: str
    status: DeliveryStatus
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    notes: Optional[str] = None
    timestamp: datetime
    created_by: str

    class Config:
        from_attributes = True


# Route Schemas
class RouteCreate(BaseModel):
    driver_id: str
    delivery_ids: List[str]
    route_name: Optional[str] = None


class RouteResponse(BaseModel):
    id: str
    driver_id: str
    route_name: str
    delivery_ids: List[str]
    total_distance_km: float
    estimated_duration_minutes: int
    optimized_waypoints: List[Dict[str, Any]]
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ETA and Distance Schemas
class ETARequest(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90)
    pickup_lng: float = Field(..., ge=-180, le=180)
    delivery_lat: float = Field(..., ge=-90, le=90)
    delivery_lng: float = Field(..., ge=-180, le=180)
    priority: DeliveryPriority = DeliveryPriority.NORMAL


class ETAResponse(BaseModel):
    distance_km: float
    estimated_duration_minutes: int
    estimated_pickup_time: datetime
    estimated_delivery_time: datetime


# Assignment Schemas
class DeliveryAssignment(BaseModel):
    delivery_id: str
    driver_id: str
    estimated_pickup_time: datetime
    estimated_delivery_time: datetime


# Search and Filter Schemas
class DeliveryFilters(BaseModel):
    status: Optional[DeliveryStatus] = None
    priority: Optional[DeliveryPriority] = None
    driver_id: Optional[str] = None
    customer_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class PaginatedDeliveryResponse(BaseModel):
    items: List[DeliveryResponse]
    total: int
    page: int
    size: int
    pages: int
