from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import CylinderSize


class QuoteRequestStatus(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BidStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class AuctionStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class QuoteRequest(Base):
    """Quote request from hospitals for oxygen cylinders."""
    __tablename__ = "quote_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    hospital_id = Column(String, nullable=False, index=True)
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    quantity = Column(Integer, nullable=False)
    delivery_address = Column(Text, nullable=False)
    delivery_latitude = Column(Float, nullable=False)
    delivery_longitude = Column(Float, nullable=False)
    required_delivery_date = Column(DateTime(timezone=True), nullable=False)
    max_delivery_distance_km = Column(Float, default=50.0)
    additional_requirements = Column(Text, nullable=True)
    status = Column(Enum(QuoteRequestStatus), default=QuoteRequestStatus.OPEN)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    bids = relationship("Bid", back_populates="quote_request", cascade="all, delete-orphan")
    auction = relationship("Auction", back_populates="quote_request", uselist=False)


class Bid(Base):
    """Vendor bids on quote requests."""
    __tablename__ = "bids"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quote_request_id = Column(String, ForeignKey("quote_requests.id"), nullable=False)
    vendor_id = Column(String, nullable=False, index=True)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    delivery_fee = Column(Float, default=0.0)
    estimated_delivery_time_hours = Column(Integer, nullable=False)
    vendor_rating = Column(Float, nullable=True)  # Cached vendor rating
    distance_km = Column(Float, nullable=True)  # Distance from vendor to delivery location
    notes = Column(Text, nullable=True)
    status = Column(Enum(BidStatus), default=BidStatus.PENDING)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    quote_request = relationship("QuoteRequest", back_populates="bids")


class Auction(Base):
    """Time-limited auction for competitive bidding."""
    __tablename__ = "auctions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quote_request_id = Column(String, ForeignKey("quote_requests.id"), nullable=False)
    starting_price = Column(Float, nullable=True)  # Optional starting price
    reserve_price = Column(Float, nullable=True)  # Minimum acceptable price
    current_best_bid_id = Column(String, nullable=True)  # Current winning bid
    current_best_price = Column(Float, nullable=True)
    participant_count = Column(Integer, default=0)
    status = Column(Enum(AuctionStatus), default=AuctionStatus.ACTIVE)
    starts_at = Column(DateTime(timezone=True), server_default=func.now())
    ends_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    quote_request = relationship("QuoteRequest", back_populates="auction")


class PriceHistory(Base):
    """Historical pricing data for analytics."""
    __tablename__ = "price_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id = Column(String, nullable=False, index=True)
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    total_value = Column(Float, nullable=False)
    delivery_location = Column(String, nullable=False)
    delivery_distance_km = Column(Float, nullable=True)
    order_id = Column(String, nullable=True)  # Reference to completed order
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())


class VendorPerformance(Base):
    """Vendor performance metrics for selection algorithms."""
    __tablename__ = "vendor_performance"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id = Column(String, nullable=False, unique=True, index=True)
    total_bids = Column(Integer, default=0)
    successful_bids = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    average_delivery_time_hours = Column(Float, nullable=True)
    average_rating = Column(Float, nullable=True)
    total_orders_completed = Column(Integer, default=0)
    total_revenue = Column(Float, default=0.0)
    last_active_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())