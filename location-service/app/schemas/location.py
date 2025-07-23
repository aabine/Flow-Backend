from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


# Location Schemas
class LocationCreate(BaseModel):
    name: str
    address: str
    city: str
    state: str
    country: str = "Nigeria"
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    location_type: str  # 'hospital', 'vendor', 'warehouse'


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    location_type: Optional[str] = None
    is_active: Optional[bool] = None


class LocationResponse(BaseModel):
    id: str
    user_id: str
    name: str
    address: str
    city: str
    state: str
    country: str
    latitude: float
    longitude: float
    location_type: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Emergency Zone Schemas
class EmergencyZoneCreate(BaseModel):
    name: str
    description: Optional[str] = None
    center_latitude: float = Field(..., ge=-90, le=90)
    center_longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(..., gt=0)
    severity_level: str  # 'low', 'medium', 'high', 'critical'
    alert_message: Optional[str] = None


class EmergencyZoneResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    center_latitude: float
    center_longitude: float
    radius_km: float
    severity_level: str
    is_active: bool
    alert_message: Optional[str] = None
    created_by: str
    activated_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Service Area Schemas
class ServiceAreaCreate(BaseModel):
    name: str
    center_latitude: float = Field(..., ge=-90, le=90)
    center_longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(..., gt=0)
    delivery_fee: float = Field(0.0, ge=0)
    minimum_order_amount: float = Field(0.0, ge=0)


class ServiceAreaResponse(BaseModel):
    id: str
    vendor_id: str
    name: str
    center_latitude: float
    center_longitude: float
    radius_km: float
    delivery_fee: float
    minimum_order_amount: float
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Search Schemas
class NearbySearchRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(50.0, gt=0)
    location_type: Optional[str] = None


class NearbySearchResponse(BaseModel):
    locations: List[LocationResponse]
    total_count: int
    search_radius_km: float
    center_latitude: float
    center_longitude: float

    class Config:
        from_attributes = True
