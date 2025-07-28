from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    HOSPITAL = "hospital"
    VENDOR = "vendor"
    ADMIN = "admin"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EMERGENCY = "emergency"


class CylinderSize(str, Enum):
    SMALL = "2 meter"  # 10L
    MEDIUM = "4 meter"  # 20L
    LARGE = "6 meter"  # 40L
    EXTRA_LARGE = "10 meter"  # 50L


class CylinderStatus(str, Enum):
    FILLED = "filled"
    EMPTY = "empty"
    IN_TRANSIT = "in_transit"
    MAINTENANCE = "maintenance"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"


class SupplierStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class NotificationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


class EventType(str, Enum):
    USER_CREATED = "user_created"
    ORDER_PLACED = "order_placed"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_DELIVERED = "order_delivered"
    INVENTORY_UPDATED = "inventory_updated"
    PAYMENT_COMPLETED = "payment_completed"
    REVIEW_CREATED = "review_created"
    EMERGENCY_ORDER = "emergency_order"


# Base Models
class BaseUser(BaseModel):
    id: Optional[str] = None
    email: str
    role: UserRole
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BaseLocation(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: str
    city: str
    state: str
    country: str = "Nigeria"


class BaseCylinder(BaseModel):
    id: Optional[str] = None
    size: CylinderSize
    status: CylinderStatus
    vendor_id: str
    location_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BaseOrder(BaseModel):
    id: Optional[str] = None
    hospital_id: str
    vendor_id: Optional[str] = None
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)
    status: OrderStatus = OrderStatus.PENDING
    is_emergency: bool = False
    delivery_address: str
    notes: Optional[str] = None
    total_amount: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BaseReview(BaseModel):
    id: Optional[str] = None
    reviewer_id: str
    reviewee_id: str
    order_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class BaseNotification(BaseModel):
    id: Optional[str] = None
    user_id: str
    type: NotificationType
    title: str
    message: str
    is_read: bool = False
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None


class BaseEvent(BaseModel):
    id: Optional[str] = None
    event_type: EventType
    source_service: str
    data: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = False


# Response Models
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
    errors: Optional[List[str]] = None


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    size: int
    pages: int


# Location Models
class LocationCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: str
    city: str
    state: str
    country: str = "Nigeria"


class LocationResponse(BaseLocation):
    id: str


# Inventory Models
class InventoryUpdate(BaseModel):
    cylinder_size: CylinderSize
    quantity_change: int
    location_id: str


class InventoryResponse(BaseModel):
    vendor_id: str
    location_id: str
    cylinder_size: CylinderSize
    available_quantity: int
    total_quantity: int
    last_updated: datetime


# Order Models
class OrderCreate(BaseModel):
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)
    delivery_address: str
    delivery_latitude: float = Field(..., ge=-90, le=90)
    delivery_longitude: float = Field(..., ge=-180, le=180)
    is_emergency: bool = False
    notes: Optional[str] = None
    preferred_vendor_id: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    vendor_id: Optional[str] = None
    notes: Optional[str] = None


# Payment Models
class PaymentCreate(BaseModel):
    order_id: str
    amount: float
    currency: str = "NGN"
    payment_method: str = "card"


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    amount: float
    currency: str
    status: PaymentStatus
    reference: str
    vendor_amount: float
    platform_fee: float
    created_at: datetime


# Review Models
class ReviewCreate(BaseModel):
    order_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ReviewResponse(BaseReview):
    reviewer_name: str
    reviewee_name: str


# Notification Models
class NotificationCreate(BaseModel):
    user_id: str
    type: NotificationType
    title: str
    message: str
    metadata: Optional[dict] = None


# Product Catalog Models
class ProductInfo(BaseModel):
    cylinder_size: CylinderSize
    unit_price: float
    available_quantity: int
    vendor_id: str
    vendor_name: str
    location_id: str
    distance_km: float
    estimated_delivery_time: int  # minutes
    vendor_rating: Optional[float] = None


class ProductCatalogItem(BaseModel):
    vendor_id: str
    vendor_name: str
    location_name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    distance_km: float
    products: List[ProductInfo]
    vendor_rating: Optional[float] = None
    is_available: bool = True
