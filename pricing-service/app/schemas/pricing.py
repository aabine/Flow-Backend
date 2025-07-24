from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import CylinderSize


# Quote Request Schemas
class QuoteRequestCreate(BaseModel):
    cylinder_size: CylinderSize
    quantity: int = Field(..., gt=0)
    delivery_address: str
    delivery_latitude: float = Field(..., ge=-90, le=90)
    delivery_longitude: float = Field(..., ge=-180, le=180)
    required_delivery_date: datetime
    max_delivery_distance_km: Optional[float] = Field(50.0, gt=0)
    additional_requirements: Optional[str] = None
    auction_duration_hours: Optional[int] = Field(24, ge=1, le=168)


class QuoteRequestUpdate(BaseModel):
    delivery_address: Optional[str] = None
    delivery_latitude: Optional[float] = Field(None, ge=-90, le=90)
    delivery_longitude: Optional[float] = Field(None, ge=-180, le=180)
    required_delivery_date: Optional[datetime] = None
    max_delivery_distance_km: Optional[float] = Field(None, gt=0)
    additional_requirements: Optional[str] = None


class QuoteRequestResponse(BaseModel):
    id: str
    hospital_id: str
    cylinder_size: CylinderSize
    quantity: int
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    required_delivery_date: datetime
    max_delivery_distance_km: float
    additional_requirements: Optional[str]
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: Optional[datetime]
    bid_count: Optional[int] = 0
    lowest_bid_price: Optional[float] = None

    class Config:
        from_attributes = True


class PaginatedQuoteRequestResponse(BaseModel):
    items: List[QuoteRequestResponse]
    total: int
    page: int
    size: int
    pages: int


# Bid Schemas
class BidCreate(BaseModel):
    unit_price: float = Field(..., gt=0)
    delivery_fee: float = Field(0.0, ge=0)
    estimated_delivery_time_hours: int = Field(..., gt=0)
    notes: Optional[str] = None


class BidUpdate(BaseModel):
    unit_price: Optional[float] = Field(None, gt=0)
    delivery_fee: Optional[float] = Field(None, ge=0)
    estimated_delivery_time_hours: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None


class BidResponse(BaseModel):
    id: str
    quote_request_id: str
    vendor_id: str
    unit_price: float
    total_price: float
    delivery_fee: float
    estimated_delivery_time_hours: int
    vendor_rating: Optional[float]
    distance_km: Optional[float]
    notes: Optional[str]
    status: str
    submitted_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PaginatedBidResponse(BaseModel):
    items: List[BidResponse]
    total: int
    page: int
    size: int
    pages: int


# Auction Schemas
class AuctionResponse(BaseModel):
    id: str
    quote_request_id: str
    starting_price: Optional[float]
    reserve_price: Optional[float]
    current_best_bid_id: Optional[str]
    current_best_price: Optional[float]
    participant_count: int
    status: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Ranking and Analytics Schemas
class BidRankingItem(BaseModel):
    bid: BidResponse
    total_score: float
    price_score: float
    rating_score: float
    distance_score: float
    delivery_time_score: float


class BidRankingResponse(BaseModel):
    quote_request_id: str
    ranked_bids: List[Dict[str, Any]]


# Vendor Performance Schemas
class VendorPerformanceResponse(BaseModel):
    vendor_id: str
    overall_success_rate: float
    recent_success_rate: float
    total_bids: int
    successful_bids: int
    average_rating: Optional[float]
    average_delivery_time_hours: Optional[float]
    total_revenue: float
    recent_bid_count: int
    recent_avg_bid_amount: float


# Price History Schemas
class PriceHistoryResponse(BaseModel):
    id: str
    vendor_id: str
    cylinder_size: CylinderSize
    unit_price: float
    quantity: int
    total_value: float
    delivery_location: str
    delivery_distance_km: Optional[float]
    order_id: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


# Analytics Schemas
class PriceTrendPoint(BaseModel):
    date: str
    average_price: float
    min_price: float
    max_price: float
    transaction_count: int


class PriceTrendsResponse(BaseModel):
    cylinder_size: str
    period_days: int
    trends: List[PriceTrendPoint]


class MarketInsightsResponse(BaseModel):
    period_days: int
    average_bids_per_request: float
    price_distribution: Dict[str, Dict[str, float]]
    geographic_distribution: List[Dict[str, Any]]
    delivery_time_analysis: Dict[str, float]