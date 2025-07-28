from sqlalchemy import Column, String, Boolean, DateTime, Text, DECIMAL, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class ProductCatalog(Base):
    """Product catalog for vendors."""
    __tablename__ = "product_catalogs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    
    # Product identification
    product_code = Column(String(100), nullable=False, index=True)
    product_name = Column(String(255), nullable=False, index=True)
    product_category = Column(String(100), nullable=False, index=True)  # oxygen_cylinder, medical_equipment, etc.
    product_subcategory = Column(String(100))
    
    # Product specifications
    cylinder_size = Column(String(20), index=True)  # For oxygen cylinders: small, medium, large, industrial
    capacity_liters = Column(DECIMAL(8, 2))
    pressure_bar = Column(DECIMAL(8, 2))
    gas_type = Column(String(50), default="medical_oxygen")  # medical_oxygen, industrial_oxygen, etc.
    purity_percentage = Column(DECIMAL(5, 2))
    
    # Physical specifications
    dimensions = Column(JSONB)  # {"height": 120, "diameter": 20, "weight": 15}
    weight_kg = Column(DECIMAL(8, 2))
    material = Column(String(100))
    color = Column(String(50))
    
    # Product details
    description = Column(Text)
    features = Column(JSONB)  # List of product features
    specifications = Column(JSONB)  # Detailed technical specifications
    usage_instructions = Column(Text)
    safety_information = Column(Text)
    
    # Compliance and certification
    certifications = Column(JSONB)  # [{"name": "ISO 13485", "number": "CERT123", "expiry": "2025-12-31"}]
    regulatory_approvals = Column(JSONB)  # FDA, NAFDAC, etc.
    quality_standards = Column(JSONB)
    
    # Media
    product_images = Column(JSONB)  # List of image URLs
    product_documents = Column(JSONB)  # Manuals, certificates, etc.
    
    # Availability
    is_available = Column(Boolean, default=True, index=True)
    stock_status = Column(String(50), default="in_stock", index=True)  # in_stock, low_stock, out_of_stock
    minimum_order_quantity = Column(Integer, default=1)
    maximum_order_quantity = Column(Integer)
    
    # Pricing reference (actual pricing in PricingTier)
    base_price = Column(DECIMAL(10, 2))
    currency = Column(String(3), default="NGN")
    
    # Vendor-specific details
    vendor_product_code = Column(String(100))  # Vendor's internal product code
    manufacturer = Column(String(255))
    brand = Column(String(100))
    model_number = Column(String(100))
    
    # Logistics
    requires_special_handling = Column(Boolean, default=False)
    hazardous_material = Column(Boolean, default=False)
    storage_requirements = Column(Text)
    shelf_life_days = Column(Integer)
    
    # SEO and search
    search_keywords = Column(JSONB)  # Keywords for search optimization
    tags = Column(JSONB)  # Product tags
    
    # Status
    is_featured = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, index=True)
    approval_status = Column(String(50), default="pending", index=True)  # pending, approved, rejected
    
    # Product metadata
    product_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True))

    # Relationships
    vendor = relationship("Vendor", back_populates="product_catalogs")
    pricing_tiers = relationship("PricingTier", back_populates="product")

    def __repr__(self):
        return f"<ProductCatalog(id={self.id}, product_name='{self.product_name}', vendor_id={self.vendor_id})>"


class ProductAvailability(Base):
    """Real-time product availability tracking."""
    __tablename__ = "product_availability"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product_catalogs.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    location_id = Column(UUID(as_uuid=True), index=True)  # Reference to location service
    
    # Availability details
    quantity_available = Column(Integer, default=0, nullable=False)
    quantity_reserved = Column(Integer, default=0)
    quantity_in_transit = Column(Integer, default=0)
    
    # Stock management
    reorder_level = Column(Integer, default=0)
    maximum_stock = Column(Integer)
    last_restocked_at = Column(DateTime(timezone=True))
    next_restock_date = Column(DateTime(timezone=True))
    
    # Location details
    warehouse_location = Column(String(255))
    storage_zone = Column(String(100))
    
    # Status
    is_available = Column(Boolean, default=True, index=True)
    availability_status = Column(String(50), default="available", index=True)  # available, limited, unavailable
    
    # Timestamps
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<ProductAvailability(id={self.id}, product_id={self.product_id}, quantity={self.quantity_available})>"


class ProductReview(Base):
    """Product reviews and ratings."""
    __tablename__ = "product_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product_catalogs.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Reference to user service
    order_id = Column(UUID(as_uuid=True), index=True)  # Reference to order service
    
    # Review content
    rating = Column(Integer, nullable=False, index=True)  # 1-5 stars
    title = Column(String(255))
    review_text = Column(Text)
    
    # Review categories
    quality_rating = Column(Integer)  # 1-5
    delivery_rating = Column(Integer)  # 1-5
    value_rating = Column(Integer)  # 1-5
    service_rating = Column(Integer)  # 1-5
    
    # Review metadata
    is_verified_purchase = Column(Boolean, default=False)
    is_anonymous = Column(Boolean, default=False)
    helpful_votes = Column(Integer, default=0)
    total_votes = Column(Integer, default=0)
    
    # Moderation
    is_approved = Column(Boolean, default=True, index=True)
    moderation_notes = Column(Text)
    moderated_by = Column(UUID(as_uuid=True))
    moderated_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ProductReview(id={self.id}, product_id={self.product_id}, rating={self.rating})>"
