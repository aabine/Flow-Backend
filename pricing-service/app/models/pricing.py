from sqlalchemy import Column, String, Boolean, DateTime, Text, DECIMAL, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class PricingTier(Base):
    """Pricing tiers for products with quantity-based pricing."""
    __tablename__ = "pricing_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product_catalogs.id"), nullable=False, index=True)
    service_area_id = Column(UUID(as_uuid=True), ForeignKey("service_areas.id"), index=True)
    
    # Pricing details
    tier_name = Column(String(100), nullable=False)  # "Standard", "Bulk", "Premium", etc.
    unit_price = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(3), default="NGN")
    
    # Quantity tiers
    minimum_quantity = Column(Integer, default=1)
    maximum_quantity = Column(Integer)
    
    # Additional fees
    delivery_fee = Column(DECIMAL(10, 2), default=0.0)
    setup_fee = Column(DECIMAL(10, 2), default=0.0)
    handling_fee = Column(DECIMAL(10, 2), default=0.0)
    emergency_surcharge = Column(DECIMAL(10, 2), default=0.0)
    
    # Discounts
    bulk_discount_percentage = Column(DECIMAL(5, 2), default=0.0)
    loyalty_discount_percentage = Column(DECIMAL(5, 2), default=0.0)
    seasonal_discount_percentage = Column(DECIMAL(5, 2), default=0.0)
    
    # Validity
    effective_from = Column(DateTime(timezone=True), nullable=False, default=func.now())
    effective_until = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, index=True)
    
    # Terms and conditions
    payment_terms = Column(String(100))  # "immediate", "net_30", "net_60", etc.
    minimum_order_value = Column(DECIMAL(10, 2))
    cancellation_policy = Column(Text)
    
    # Priority and ranking
    priority_rank = Column(Integer, default=1)  # For sorting pricing options
    is_featured = Column(Boolean, default=False)
    is_promotional = Column(Boolean, default=False)
    
    # Metadata
    pricing_notes = Column(Text)
    internal_notes = Column(Text)
    pricing_metadata = Column(JSONB)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", back_populates="pricing_tiers")
    product = relationship("ProductCatalog", back_populates="pricing_tiers")
    service_area = relationship("ServiceArea")

    def __repr__(self):
        return f"<PricingTier(id={self.id}, tier_name='{self.tier_name}', unit_price={self.unit_price})>"


class PriceHistory(Base):
    """Historical pricing data for analytics."""
    __tablename__ = "price_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pricing_tier_id = Column(UUID(as_uuid=True), ForeignKey("pricing_tiers.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("product_catalogs.id"), nullable=False, index=True)
    
    # Historical pricing
    old_unit_price = Column(DECIMAL(10, 2))
    new_unit_price = Column(DECIMAL(10, 2))
    old_delivery_fee = Column(DECIMAL(10, 2))
    new_delivery_fee = Column(DECIMAL(10, 2))
    
    # Change details
    change_type = Column(String(50), nullable=False, index=True)  # "price_increase", "price_decrease", "new_tier", "discontinued"
    change_percentage = Column(DECIMAL(5, 2))
    change_reason = Column(String(255))
    change_notes = Column(Text)
    
    # Context
    market_conditions = Column(JSONB)
    competitor_pricing = Column(JSONB)
    
    # Timestamps
    effective_date = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<PriceHistory(id={self.id}, change_type='{self.change_type}', effective_date={self.effective_date})>"


class PriceAlert(Base):
    """Price alerts for users monitoring specific products."""
    __tablename__ = "price_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Reference to user service
    product_id = Column(UUID(as_uuid=True), ForeignKey("product_catalogs.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), index=True)  # Optional: specific vendor
    
    # Alert criteria
    alert_type = Column(String(50), nullable=False, index=True)  # "price_drop", "price_increase", "availability", "new_vendor"
    target_price = Column(DECIMAL(10, 2))  # Alert when price reaches this level
    price_threshold_percentage = Column(DECIMAL(5, 2))  # Alert on X% change
    
    # Alert settings
    is_active = Column(Boolean, default=True, index=True)
    notification_method = Column(String(50), default="email")  # email, sms, push, in_app
    frequency = Column(String(50), default="immediate")  # immediate, daily, weekly
    
    # Tracking
    last_triggered_at = Column(DateTime(timezone=True))
    trigger_count = Column(Integer, default=0)
    last_price_checked = Column(DECIMAL(10, 2))
    
    # Expiry
    expires_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PriceAlert(id={self.id}, user_id={self.user_id}, alert_type='{self.alert_type}')>"


class MarketPricing(Base):
    """Market pricing analysis and benchmarks."""
    __tablename__ = "market_pricing"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_category = Column(String(100), nullable=False, index=True)
    cylinder_size = Column(String(20), index=True)
    geographic_area = Column(String(100), nullable=False, index=True)  # State, city, or region
    
    # Market statistics
    average_price = Column(DECIMAL(10, 2), nullable=False)
    median_price = Column(DECIMAL(10, 2))
    minimum_price = Column(DECIMAL(10, 2))
    maximum_price = Column(DECIMAL(10, 2))
    price_standard_deviation = Column(DECIMAL(10, 2))
    
    # Market data
    vendor_count = Column(Integer, default=0)
    total_listings = Column(Integer, default=0)
    active_listings = Column(Integer, default=0)
    
    # Trends
    price_trend = Column(String(50))  # "increasing", "decreasing", "stable"
    trend_percentage = Column(DECIMAL(5, 2))
    
    # Analysis period
    analysis_date = Column(DateTime(timezone=True), nullable=False, index=True)
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    
    # Metadata
    data_sources = Column(JSONB)
    analysis_notes = Column(Text)
    confidence_score = Column(DECIMAL(3, 2))  # 0.0 to 1.0
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<MarketPricing(id={self.id}, product_category='{self.product_category}', average_price={self.average_price})>"
