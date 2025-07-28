from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


class CylinderSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    INDUSTRIAL = "industrial"


class ProductCategory(str, Enum):
    OXYGEN_CYLINDER = "oxygen_cylinder"
    MEDICAL_EQUIPMENT = "medical_equipment"
    ACCESSORIES = "accessories"
    CONSUMABLES = "consumables"


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProductBase(BaseModel):
    """Base product schema."""
    product_code: str = Field(..., min_length=2, max_length=100)
    product_name: str = Field(..., min_length=2, max_length=255)
    product_category: ProductCategory
    product_subcategory: Optional[str] = Field(None, max_length=100)
    cylinder_size: Optional[CylinderSize] = None
    capacity_liters: Optional[Decimal] = Field(None, gt=0)
    pressure_bar: Optional[Decimal] = Field(None, gt=0)
    gas_type: str = Field("medical_oxygen", max_length=50)
    purity_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    weight_kg: Optional[Decimal] = Field(None, gt=0)
    material: Optional[str] = Field(None, max_length=100)
    color: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    usage_instructions: Optional[str] = None
    safety_information: Optional[str] = None
    minimum_order_quantity: int = Field(1, ge=1)
    maximum_order_quantity: Optional[int] = Field(None, ge=1)
    base_price: Optional[Decimal] = Field(None, gt=0)
    currency: str = Field("NGN", max_length=3)
    vendor_product_code: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=255)
    brand: Optional[str] = Field(None, max_length=100)
    model_number: Optional[str] = Field(None, max_length=100)
    requires_special_handling: bool = False
    hazardous_material: bool = False
    storage_requirements: Optional[str] = None
    shelf_life_days: Optional[int] = Field(None, gt=0)


class ProductCreate(ProductBase):
    """Schema for creating a product."""
    pass


class ProductUpdate(BaseModel):
    """Schema for updating product information."""
    product_name: Optional[str] = Field(None, min_length=2, max_length=255)
    product_subcategory: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    usage_instructions: Optional[str] = None
    safety_information: Optional[str] = None
    minimum_order_quantity: Optional[int] = Field(None, ge=1)
    maximum_order_quantity: Optional[int] = Field(None, ge=1)
    base_price: Optional[Decimal] = Field(None, gt=0)
    requires_special_handling: Optional[bool] = None
    hazardous_material: Optional[bool] = None
    storage_requirements: Optional[str] = None
    shelf_life_days: Optional[int] = Field(None, gt=0)
    is_available: Optional[bool] = None
    is_featured: Optional[bool] = None


class ProductResponse(ProductBase):
    """Schema for product response."""
    id: str
    vendor_id: str
    dimensions: Optional[Dict[str, Any]] = None
    features: Optional[List[str]] = None
    specifications: Optional[Dict[str, Any]] = None
    certifications: Optional[List[Dict[str, Any]]] = None
    regulatory_approvals: Optional[List[str]] = None
    quality_standards: Optional[List[str]] = None
    product_images: Optional[List[str]] = None
    product_documents: Optional[List[Dict[str, str]]] = None
    is_available: bool
    stock_status: StockStatus
    is_featured: bool
    is_active: bool
    approval_status: ApprovalStatus
    search_keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Schema for product list response."""
    products: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSearchRequest(BaseModel):
    """Schema for product search request."""
    query: Optional[str] = Field(None, max_length=255)
    product_category: Optional[ProductCategory] = None
    cylinder_size: Optional[CylinderSize] = None
    vendor_id: Optional[str] = None
    min_price: Optional[Decimal] = Field(None, ge=0)
    max_price: Optional[Decimal] = Field(None, ge=0)
    in_stock_only: bool = True
    featured_only: bool = False
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, gt=0, le=200)
    sort_by: str = Field("relevance", pattern="^(relevance|price_asc|price_desc|rating|distance|newest)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class ProductCatalogItem(BaseModel):
    """Schema for product catalog item with vendor and pricing info."""
    product_id: str
    vendor_id: str
    vendor_name: str
    business_name: str
    product_name: str
    product_category: ProductCategory
    cylinder_size: Optional[CylinderSize] = None
    capacity_liters: Optional[Decimal] = None
    description: Optional[str] = None
    base_price: Decimal
    currency: str
    minimum_order_quantity: int
    maximum_order_quantity: Optional[int] = None
    is_available: bool
    stock_status: StockStatus
    vendor_rating: Optional[Decimal] = None
    distance_km: Optional[float] = None
    estimated_delivery_hours: Optional[int] = None
    delivery_fee: Optional[Decimal] = None
    emergency_surcharge: Optional[Decimal] = None
    product_images: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    features: Optional[List[str]] = None


class ProductCatalogResponse(BaseModel):
    """Schema for product catalog response."""
    items: List[ProductCatalogItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    search_criteria: ProductSearchRequest
    filters_applied: Dict[str, Any]


class ProductAvailabilityRequest(BaseModel):
    """Schema for checking product availability."""
    product_ids: List[str] = Field(..., min_items=1, max_items=50)
    quantity: int = Field(1, ge=1)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, gt=0, le=200)


class ProductAvailabilityItem(BaseModel):
    """Schema for product availability item."""
    product_id: str
    vendor_id: str
    vendor_name: str
    available_quantity: int
    reserved_quantity: int
    is_available: bool
    estimated_delivery_hours: int
    unit_price: Decimal
    delivery_fee: Decimal
    total_price: Decimal


class ProductAvailabilityResponse(BaseModel):
    """Schema for product availability response."""
    items: List[ProductAvailabilityItem]
    requested_quantity: int
    total_available_vendors: int
    search_radius_km: float
