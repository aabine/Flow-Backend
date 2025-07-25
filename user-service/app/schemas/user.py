from pydantic import BaseModel, EmailStr, Field, pattern
from typing import Optional
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import UserRole, SupplierStatus


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
    registration_number: Optional[str] = None  # Standardized field name
    tax_identification_number: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    business_address: Optional[str] = None
    delivery_radius_km: Optional[float] = None  # Fixed data type
    operating_hours: Optional[str] = None
    emergency_service: bool = False
    minimum_order_value: Optional[float] = None  # Fixed data type
    payment_terms: Optional[str] = None
    supplier_onboarding_status: SupplierStatus = SupplierStatus.PENDING_VERIFICATION  # Fixed enum usage
    supplier_onboarding_response_time: Optional[datetime] = None


class VendorProfileResponse(VendorProfileCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Password Management Schemas
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str


class PasswordValidationResponse(BaseModel):
    is_valid: bool
    errors: list[str]
    strength: str  # weak, medium, strong
    score: int


# Session Management Schemas
class LoginWithRememberMe(UserLogin):
    remember_me: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class EnhancedTokenResponse(TokenResponse):
    refresh_token: str
    session_id: str


class UserSessionResponse(BaseModel):
    id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_current: bool = False


# Email Verification Schemas
class EmailVerificationRequest(BaseModel):
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    token: str


# MFA Schemas
class MFASetupRequest(BaseModel):
    device_name: str = "Authenticator App"
    device_type: str = "totp"


class MFASetupResponse(BaseModel):
    device_id: str
    secret_key: str
    qr_code: str
    backup_codes: list[str]
    device_name: str
    setup_complete: bool


class MFAVerificationRequest(BaseModel):
    device_id: str
    verification_code: str


class MFALoginRequest(BaseModel):
    mfa_token: str
    verification_code: str


class MFADisableRequest(BaseModel):
    verification_code: str


class MFADeviceResponse(BaseModel):
    id: str
    device_type: str
    device_name: str
    is_active: bool
    last_used: Optional[datetime]
    created_at: datetime


class BackupCodesResponse(BaseModel):
    backup_codes: list[str]


# Additional Session Management Schemas
class SessionInfoResponse(BaseModel):
    id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_current: bool = False
    location: Optional[str] = None  # Could be added later with IP geolocation
    device_type: Optional[str] = None  # Could be parsed from user agent


class ActiveSessionsResponse(BaseModel):
    sessions: list[SessionInfoResponse]
    total_count: int
    current_session_id: Optional[str]


# API Key Management Schemas
class APIKeyCreateRequest(BaseModel):
    key_name: str = Field(..., min_length=1, max_length=100)
    permissions: list[str]
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650)  # Max 10 years


class APIKeyResponse(BaseModel):
    id: str
    key_name: str
    key_prefix: str
    permissions: list[str]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    created_at: datetime
    user_id: Optional[str]


class APIKeyCreateResponse(BaseModel):
    id: str
    api_key: str
    key_name: str
    key_prefix: str
    permissions: list[str]
    expires_at: Optional[datetime]
    created_at: datetime
    warning: str


# OAuth/Social Login Schemas
class OAuthAuthURLRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(google|facebook)$")
    role: Optional[str] = Field(None, pattern=r"^(admin|vendor|hospital)$")


class OAuthAuthURLResponse(BaseModel):
    auth_url: str
    state: str
    provider: str


class OAuthCallbackRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(google|facebook)$")
    code: str
    state: str


class OAuthLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    session_id: str
    user: UserResponse
    oauth_provider: str
    is_new_user: bool
