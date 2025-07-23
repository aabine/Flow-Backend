from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import UserRole


class UserBase(BaseModel):
    email: EmailStr
    role: UserRole


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: UserResponse


class HospitalProfileCreate(BaseModel):
    hospital_name: str
    registration_number: Optional[str] = None
    license_number: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    bed_capacity: Optional[str] = None
    hospital_type: Optional[str] = None
    services_offered: Optional[str] = None


class HospitalProfileResponse(HospitalProfileCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VendorProfileCreate(BaseModel):
    business_name: str
    business_registration_number: Optional[str] = None
    tax_identification_number: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    business_address: Optional[str] = None
    delivery_radius_km: Optional[str] = None
    operating_hours: Optional[str] = None
    emergency_service: bool = False
    minimum_order_value: Optional[str] = None
    payment_terms: Optional[str] = None
    supplier_onboarding_status: str = "unreachable"
    supplier_onboarding_response_time: Optional[datetime] = None


class VendorProfileResponse(VendorProfileCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
