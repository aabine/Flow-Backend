from sqlalchemy import Column, String, Boolean, DateTime, Text, DECIMAL, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class Vendor(Base):
    """Vendor model for storing vendor information."""
    __tablename__ = "vendors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)  # FK to users table
    business_name = Column(String(255), nullable=False, index=True)
    business_registration_number = Column(String(100))
    tax_identification_number = Column(String(100))
    contact_person = Column(String(255))
    contact_phone = Column(String(20))
    contact_email = Column(String(255))
    business_address = Column(Text)
    business_city = Column(String(100))
    business_state = Column(String(100))
    business_country = Column(String(100), default="Nigeria")
    postal_code = Column(String(20))
    
    # Business details
    business_type = Column(String(50), default="medical_supplier")  # medical_supplier, distributor, manufacturer
    years_in_business = Column(Integer)
    license_number = Column(String(100))
    certification_details = Column(JSONB)
    
    # Status and verification
    verification_status = Column(String(50), default="pending", index=True)  # pending, verified, rejected, suspended
    is_active = Column(Boolean, default=True, index=True)
    is_featured = Column(Boolean, default=False)
    rejection_reason = Column(Text)
    
    # Performance metrics
    average_rating = Column(DECIMAL(3, 2), default=0.0)
    total_orders = Column(Integer, default=0)
    successful_deliveries = Column(Integer, default=0)
    response_time_hours = Column(DECIMAL(5, 2), default=24.0)
    
    # Operational details
    operating_hours = Column(JSONB)  # {"monday": {"open": "08:00", "close": "18:00"}, ...}
    emergency_contact = Column(String(20))
    emergency_surcharge_percentage = Column(DECIMAL(5, 2), default=0.0)
    minimum_order_value = Column(DECIMAL(10, 2), default=0.0)
    
    # Vendor metadata
    vendor_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    verified_at = Column(DateTime(timezone=True))
    last_active_at = Column(DateTime(timezone=True))

    # Relationships
    vendor_profile = relationship("VendorProfile", back_populates="vendor", uselist=False)
    service_areas = relationship("ServiceArea", back_populates="vendor")
    product_catalogs = relationship("ProductCatalog", back_populates="vendor")
    pricing_tiers = relationship("PricingTier", back_populates="vendor")

    def __repr__(self):
        return f"<Vendor(id={self.id}, business_name='{self.business_name}', status='{self.verification_status}')>"


class VendorProfile(Base):
    """Extended vendor profile information."""
    __tablename__ = "vendor_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, unique=True, index=True)
    
    # Company details
    company_description = Column(Text)
    company_logo_url = Column(String(500))
    website_url = Column(String(255))
    social_media_links = Column(JSONB)  # {"facebook": "url", "twitter": "url", ...}
    
    # Capabilities
    specializations = Column(JSONB)  # ["oxygen_cylinders", "medical_equipment", ...]
    certifications = Column(JSONB)  # [{"name": "ISO 9001", "expiry": "2025-12-31"}, ...]
    quality_standards = Column(JSONB)
    
    # Service details
    delivery_methods = Column(JSONB)  # ["standard", "express", "emergency"]
    payment_methods = Column(JSONB)  # ["cash", "card", "bank_transfer", "credit"]
    return_policy = Column(Text)
    warranty_policy = Column(Text)
    
    # Geographic coverage
    coverage_areas = Column(JSONB)  # [{"state": "Lagos", "cities": ["Lagos", "Ikeja"]}, ...]
    delivery_zones = Column(JSONB)
    
    # Performance metrics
    on_time_delivery_rate = Column(DECIMAL(5, 2), default=0.0)
    customer_satisfaction_score = Column(DECIMAL(3, 2), default=0.0)
    order_fulfillment_rate = Column(DECIMAL(5, 2), default=0.0)
    
    # Preferences
    preferred_communication_method = Column(String(50), default="email")
    notification_preferences = Column(JSONB)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", back_populates="vendor_profile")

    def __repr__(self):
        return f"<VendorProfile(id={self.id}, vendor_id={self.vendor_id})>"


class ServiceArea(Base):
    """Vendor service coverage areas."""
    __tablename__ = "service_areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    
    # Geographic definition
    area_name = Column(String(255), nullable=False)
    area_type = Column(String(50), nullable=False)  # city, state, radius, polygon
    
    # For radius-based areas
    center_latitude = Column(DECIMAL(10, 8))
    center_longitude = Column(DECIMAL(11, 8))
    radius_km = Column(DECIMAL(8, 2))
    
    # For polygon/boundary areas
    boundary_coordinates = Column(JSONB)  # GeoJSON polygon
    
    # Administrative areas
    state = Column(String(100))
    cities = Column(JSONB)  # List of cities covered
    postal_codes = Column(JSONB)  # List of postal codes covered
    
    # Service details
    delivery_fee = Column(DECIMAL(10, 2), default=0.0)
    minimum_order_value = Column(DECIMAL(10, 2), default=0.0)
    estimated_delivery_time_hours = Column(Integer, default=24)
    emergency_delivery_available = Column(Boolean, default=False)
    emergency_delivery_time_hours = Column(Integer)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    priority_level = Column(Integer, default=1)  # 1=highest, 5=lowest
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", back_populates="service_areas")

    def __repr__(self):
        return f"<ServiceArea(id={self.id}, vendor_id={self.vendor_id}, area_name='{self.area_name}')>"
