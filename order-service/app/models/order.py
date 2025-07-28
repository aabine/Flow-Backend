from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import OrderStatus, CylinderSize


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    reference = Column(String, unique=True, index=True, nullable=False)
    hospital_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    status = Column(ENUM('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', name='orderstatus'), default='pending', index=True)
    is_emergency = Column(Boolean, default=False, index=True)
    
    # Delivery information
    delivery_address = Column(Text, nullable=False)
    delivery_latitude = Column(Float, nullable=False)
    delivery_longitude = Column(Float, nullable=False)
    delivery_contact_name = Column(String, nullable=True)
    delivery_contact_phone = Column(String, nullable=True)
    
    # Order details
    notes = Column(Text, nullable=True)
    special_instructions = Column(Text, nullable=True)
    
    # Pricing
    subtotal = Column(Float, nullable=True)
    delivery_fee = Column(Float, nullable=True)
    emergency_surcharge = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)
    
    # Timing
    requested_delivery_time = Column(DateTime(timezone=True), nullable=True)
    estimated_delivery_time = Column(DateTime(timezone=True), nullable=True)
    actual_delivery_time = Column(DateTime(timezone=True), nullable=True)
    
    # Tracking
    tracking_number = Column(String, nullable=True)
    delivery_notes = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    cylinder_size = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    order = relationship("Order", back_populates="items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    status = Column(ENUM('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', name='orderstatus'), nullable=False)
    notes = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    order = relationship("Order", back_populates="status_history")
