from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class BusinessType(str, Enum):
    MEDICAL_SUPPLIER = "medical_supplier"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"


class VendorBase(BaseModel):
    """Base vendor schema."""
    business_name: str = Field(..., min_length=2, max_length=255)
    business_registration_number: Optional[str] = Field(None, max_length=100)
    tax_identification_number: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=20)
    contact_email: Optional[str] = Field(None, max_length=255)
    business_address: Optional[str] = None
    business_city: Optional[str] = Field(None, max_length=100)
    business_state: Optional[str] = Field(None, max_length=100)
    business_country: str = Field("Nigeria", max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    business_type: BusinessType = BusinessType.MEDICAL_SUPPLIER
    years_in_business: Optional[int] = Field(None, ge=0, le=100)
    license_number: Optional[str] = Field(None, max_length=100)
    emergency_contact: Optional[str] = Field(None, max_length=20)
    emergency_surcharge_percentage: Decimal = Field(Decimal("0.0"), ge=0, le=100)
    minimum_order_value: Decimal = Field(Decimal("0.0"), ge=0)


class VendorCreate(VendorBase):
    """Schema for creating a vendor."""
    user_id: str = Field(..., description="User ID from user service")


class VendorUpdate(BaseModel):
    """Schema for updating vendor information."""
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    contact_person: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=20)
    contact_email: Optional[str] = Field(None, max_length=255)
    business_address: Optional[str] = None
    business_city: Optional[str] = Field(None, max_length=100)
    business_state: Optional[str] = Field(None, max_length=100)
    emergency_contact: Optional[str] = Field(None, max_length=20)
    emergency_surcharge_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    minimum_order_value: Optional[Decimal] = Field(None, ge=0)
    operating_hours: Optional[Dict[str, Any]] = None


class VendorResponse(VendorBase):
    """Schema for vendor response."""
    id: str
    user_id: str
    verification_status: VerificationStatus
    is_active: bool
    is_featured: bool
    average_rating: Decimal
    total_orders: int
    successful_deliveries: int
    response_time_hours: Decimal
    operating_hours: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VendorListResponse(BaseModel):
    """Schema for vendor list response."""
    vendors: List[VendorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class VendorSearchRequest(BaseModel):
    """Schema for vendor search request."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(50.0, gt=0, le=200)
    business_type: Optional[BusinessType] = None
    verification_status: Optional[VerificationStatus] = None
    minimum_rating: Optional[float] = Field(None, ge=0, le=5)
    emergency_delivery: Optional[bool] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class ServiceAreaBase(BaseModel):
    """Base service area schema."""
    area_name: str = Field(..., min_length=2, max_length=255, description="Name of service area")
    area_type: str = Field(..., pattern=r"^(city|state|radius|polygon)$", description="Type of service area")
    center_latitude: Optional[Decimal] = Field(None, ge=-90, le=90, description="Center latitude of service area")
    center_longitude: Optional[Decimal] = Field(None, ge=-180, le=180, description="Center longitude of service area")
    radius_km: Optional[Decimal] = Field(None, gt=0, le=1000, description="Radius of service area in kilometers")
    state: Optional[str] = Field(None, max_length=100, description="State of service area")
    cities: Optional[List[str]] = None  # List of cities covered
    delivery_fee: Decimal = Field(Decimal("0.0"), ge=0, description="Delivery fee for this service area")
    minimum_order_value: Decimal = Field(Decimal("0.0"), ge=0, description="Minimum order value for this service area")
    estimated_delivery_time_hours: int = Field(24, ge=1, le=168, description="Estimated delivery time for this service area")
    emergency_delivery_available: bool = False  # Whether emergency delivery is available for this service area
    emergency_delivery_time_hours: Optional[int] = Field(None, ge=1, le=24, description="Emergency delivery time for this service area")
    boundary_coordinates: Optional[Dict[str, Any]] = None  # GeoJSON polygon
    postal_codes: Optional[List[str]] = None  # List of postal codes covered


class ServiceAreaCreate(ServiceAreaBase):
    """Schema for creating a service area."""
    vendor_id: str = Field(..., description="Vendor ID that this service area belongs to")


class ServiceAreaUpdate(BaseModel):
    """Schema for updating a service area."""
    area_name: Optional[str] = Field(None, min_length=2, max_length=255)
    delivery_fee: Optional[Decimal] = Field(None, ge=0)
    minimum_order_value: Optional[Decimal] = Field(None, ge=0)
    estimated_delivery_time_hours: Optional[int] = Field(None, ge=1, le=168)
    emergency_delivery_available: Optional[bool] = None
    emergency_delivery_time_hours: Optional[int] = Field(None, ge=1, le=24)
    is_active: Optional[bool] = None


class ServiceAreaResponse(ServiceAreaBase):
    """Schema for service area response."""
    id: str
    vendor_id: str
    is_active: bool
    priority_level: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
