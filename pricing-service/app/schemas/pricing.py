from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


class PricingTierBase(BaseModel):
    """Base pricing tier schema."""
    tier_name: str = Field(..., min_length=2, max_length=100)
    unit_price: Decimal = Field(..., gt=0)
    currency: str = Field("NGN", max_length=3)
    minimum_quantity: int = Field(1, ge=1)
    maximum_quantity: Optional[int] = Field(None, ge=1)
    delivery_fee: Decimal = Field(Decimal("0.0"), ge=0)
    setup_fee: Decimal = Field(Decimal("0.0"), ge=0)
    handling_fee: Decimal = Field(Decimal("0.0"), ge=0)
    emergency_surcharge: Decimal = Field(Decimal("0.0"), ge=0)
    bulk_discount_percentage: Decimal = Field(Decimal("0.0"), ge=0, le=100)
    loyalty_discount_percentage: Decimal = Field(Decimal("0.0"), ge=0, le=100)
    seasonal_discount_percentage: Decimal = Field(Decimal("0.0"), ge=0, le=100)
    payment_terms: Optional[str] = Field(None, max_length=100)
    minimum_order_value: Optional[Decimal] = Field(None, ge=0)
    cancellation_policy: Optional[str] = None
    pricing_notes: Optional[str] = None


class PricingTierCreate(PricingTierBase):
    """Schema for creating a pricing tier."""
    product_id: str = Field(..., description="Product ID")
    service_area_id: Optional[str] = Field(None, description="Service area ID")
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None


class PricingTierUpdate(BaseModel):
    """Schema for updating pricing tier."""
    tier_name: Optional[str] = Field(None, min_length=2, max_length=100)
    unit_price: Optional[Decimal] = Field(None, gt=0)
    minimum_quantity: Optional[int] = Field(None, ge=1)
    maximum_quantity: Optional[int] = Field(None, ge=1)
    delivery_fee: Optional[Decimal] = Field(None, ge=0)
    setup_fee: Optional[Decimal] = Field(None, ge=0)
    handling_fee: Optional[Decimal] = Field(None, ge=0)
    emergency_surcharge: Optional[Decimal] = Field(None, ge=0)
    bulk_discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    loyalty_discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    seasonal_discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    payment_terms: Optional[str] = Field(None, max_length=100)
    minimum_order_value: Optional[Decimal] = Field(None, ge=0)
    cancellation_policy: Optional[str] = None
    pricing_notes: Optional[str] = None
    effective_until: Optional[datetime] = None
    is_active: Optional[bool] = None


class PricingTierResponse(PricingTierBase):
    """Schema for pricing tier response."""
    id: str
    vendor_id: str
    product_id: str
    service_area_id: Optional[str] = None
    effective_from: datetime
    effective_until: Optional[datetime] = None
    is_active: bool
    priority_rank: int
    is_featured: bool
    is_promotional: bool
    internal_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PriceComparisonRequest(BaseModel):
    """Schema for price comparison request."""
    product_id: Optional[str] = None
    product_category: Optional[str] = None
    cylinder_size: Optional[str] = None
    quantity: int = Field(1, ge=1)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(50.0, gt=0, le=200)
    include_emergency_pricing: bool = False
    sort_by: str = Field("price", pattern="^(price|distance|rating|delivery_time)$")
    max_results: int = Field(10, ge=1, le=50)


class VendorPricingOption(BaseModel):
    """Schema for vendor pricing option in comparison."""
    vendor_id: str
    vendor_name: str
    business_name: str
    product_id: str
    product_name: str
    tier_id: str
    tier_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    delivery_fee: Decimal
    setup_fee: Decimal
    handling_fee: Decimal
    emergency_surcharge: Decimal
    total_discount: Decimal
    total_price: Decimal
    currency: str
    distance_km: float
    estimated_delivery_hours: int
    vendor_rating: Optional[Decimal] = None
    payment_terms: Optional[str] = None
    minimum_order_value: Optional[Decimal] = None
    is_emergency_available: bool
    certifications: Optional[List[str]] = None


class PriceComparisonResponse(BaseModel):
    """Schema for price comparison response."""
    options: List[VendorPricingOption]
    best_price_option: Optional[VendorPricingOption] = None
    fastest_delivery_option: Optional[VendorPricingOption] = None
    highest_rated_option: Optional[VendorPricingOption] = None
    closest_vendor_option: Optional[VendorPricingOption] = None
    comparison_summary: Dict[str, Any]
    search_criteria: PriceComparisonRequest
    total_vendors_found: int
    search_timestamp: datetime


class BulkPricingRequest(BaseModel):
    """Schema for bulk pricing request."""
    items: List[Dict[str, Any]] = Field(..., min_items=1, max_items=100)
    vendor_id: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(50.0, gt=0, le=200)
    include_emergency_pricing: bool = False
    preferred_vendor_ids: Optional[List[str]] = None


class BulkPricingItem(BaseModel):
    """Schema for bulk pricing item."""
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    delivery_fee: Decimal
    total_price: Decimal


class BulkPricingOption(BaseModel):
    """Schema for bulk pricing option from a vendor."""
    vendor_id: str
    vendor_name: str
    business_name: str
    items: List[BulkPricingItem]
    subtotal: Decimal
    total_delivery_fee: Decimal
    bulk_discount: Decimal
    total_price: Decimal
    currency: str
    estimated_delivery_hours: int
    vendor_rating: Optional[Decimal] = None
    distance_km: float


class BulkPricingResponse(BaseModel):
    """Schema for bulk pricing response."""
    options: List[BulkPricingOption]
    best_price_option: Optional[BulkPricingOption] = None
    recommended_option: Optional[BulkPricingOption] = None
    total_vendors_found: int
    search_criteria: BulkPricingRequest


class PriceAlertCreate(BaseModel):
    """Schema for creating price alert."""
    product_id: str
    vendor_id: Optional[str] = None
    alert_type: str = Field(..., pattern="^(price_drop|price_increase|availability|new_vendor)$")
    target_price: Optional[Decimal] = Field(None, gt=0)
    price_threshold_percentage: Optional[Decimal] = Field(None, gt=0, le=100)
    notification_method: str = Field("email", pattern="^(email|sms|push|in_app)$")
    frequency: str = Field("immediate", pattern="^(immediate|daily|weekly)$")
    expires_at: Optional[datetime] = None


class PriceAlertResponse(BaseModel):
    """Schema for price alert response."""
    id: str
    user_id: str
    product_id: str
    vendor_id: Optional[str] = None
    alert_type: str
    target_price: Optional[Decimal] = None
    price_threshold_percentage: Optional[Decimal] = None
    notification_method: str
    frequency: str
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    trigger_count: int
    last_price_checked: Optional[Decimal] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MarketPricingResponse(BaseModel):
    """Schema for market pricing analysis response."""
    product_category: str
    cylinder_size: Optional[str] = None
    geographic_area: str
    average_price: Decimal
    median_price: Optional[Decimal] = None
    minimum_price: Decimal
    maximum_price: Decimal
    price_standard_deviation: Optional[Decimal] = None
    vendor_count: int
    total_listings: int
    active_listings: int
    price_trend: Optional[str] = None
    trend_percentage: Optional[Decimal] = None
    analysis_date: datetime
    confidence_score: Optional[Decimal] = None

    class Config:
        from_attributes = True
