from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum, Integer, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)  # Renamed for clarity
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)  # Renamed for clarity
    mfa_enabled = Column(Boolean, default=False)  # MFA support
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    mfa_devices = relationship("MFADevice", back_populates="user", cascade="all, delete-orphan")
    login_attempts = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")

    # Indexes for security queries
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_role_active', 'role', 'is_active'),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    country = Column(String, default="Nigeria")
    avatar_url = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class HospitalProfile(Base):
    __tablename__ = "hospital_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    hospital_name = Column(String, nullable=False)
    registration_number = Column(String, nullable=True)
    license_number = Column(String, nullable=True)
    contact_person = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)
    bed_capacity = Column(String, nullable=True)
    hospital_type = Column(String, nullable=True)  # public, private, specialist
    services_offered = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class VendorProfile(Base):
    __tablename__ = "vendor_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    business_name = Column(String, nullable=False)
    business_registration_number = Column(String, nullable=True)
    tax_identification_number = Column(String, nullable=True)
    contact_person = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    business_address = Column(Text, nullable=True)
    delivery_radius_km = Column(String, nullable=True)
    operating_hours = Column(String, nullable=True)
    emergency_service = Column(Boolean, default=False)
    minimum_order_value = Column(String, nullable=True)
    payment_terms = Column(String, nullable=True)
    supplier_onboarding_status = Column(String, default="unreachable")
    supplier_onboarding_response_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserSession(Base):
    """User session tracking for security and session management."""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    access_token_jti = Column(String, nullable=False, unique=True, index=True)  # JWT ID
    refresh_token_jti = Column(String, nullable=True, index=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
    logged_out_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationship
    user = relationship("User", back_populates="sessions")

    # Indexes for performance
    __table_args__ = (
        Index('idx_session_user_active', 'user_id', 'is_active'),
        Index('idx_session_token_active', 'access_token_jti', 'is_active'),
        Index('idx_session_expires', 'expires_at'),
    )


class MFADevice(Base):
    """Multi-factor authentication devices for users."""
    __tablename__ = "mfa_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    device_type = Column(String, nullable=False)  # 'totp', 'sms', 'email'
    device_name = Column(String, nullable=True)  # User-friendly name
    secret_key = Column(Text, nullable=False)  # Encrypted secret
    backup_codes = Column(Text, nullable=True)  # Encrypted backup codes
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", back_populates="mfa_devices")

    # Indexes
    __table_args__ = (
        Index('idx_mfa_user_active', 'user_id', 'is_active'),
        Index('idx_mfa_type_active', 'device_type', 'is_active'),
    )


class LoginAttempt(Base):
    """Login attempt tracking for security monitoring."""
    __tablename__ = "login_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String, nullable=True)  # 'invalid_password', 'user_not_found', etc.
    attempted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", back_populates="login_attempts")

    # Indexes for security queries
    __table_args__ = (
        Index('idx_login_email_time', 'email', 'attempted_at'),
        Index('idx_login_ip_time', 'ip_address', 'attempted_at'),
        Index('idx_login_success_time', 'success', 'attempted_at'),
    )


class PasswordResetToken(Base):
    """Password reset tokens for secure password recovery."""
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)  # Hashed token
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)

    # Indexes
    __table_args__ = (
        Index('idx_reset_token_expires', 'token_hash', 'expires_at'),
        Index('idx_reset_user_expires', 'user_id', 'expires_at'),
    )


class SecurityEvent(Base):
    """Security events for audit logging."""
    __tablename__ = "security_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    event_data = Column(Text, nullable=True)  # JSON data
    ip_address = Column(String, nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for security monitoring
    __table_args__ = (
        Index('idx_security_event_type_time', 'event_type', 'created_at'),
        Index('idx_security_event_user_time', 'user_id', 'created_at'),
        Index('idx_security_event_ip_time', 'ip_address', 'created_at'),
    )
