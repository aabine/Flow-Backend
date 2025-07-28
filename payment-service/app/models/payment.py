from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import PaymentStatus


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    reference = Column(String, nullable=False, unique=True, index=True)
    amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False, default=0.0)
    vendor_amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False, default="NGN")
    status = Column(ENUM('pending', 'processing', 'completed', 'failed', 'refunded', name='paymentstatus'), nullable=False, default='pending')
    paystack_reference = Column(String, nullable=True, unique=True)
    paystack_access_code = Column(String, nullable=True)
    authorization_url = Column(Text, nullable=True)
    payment_method = Column(String, nullable=False, default="card")
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    splits = relationship("PaymentSplit", back_populates="payment", cascade="all, delete-orphan")
    webhooks = relationship("PaymentWebhook", back_populates="payment", cascade="all, delete-orphan")


class PaymentSplit(Base):
    __tablename__ = "payment_splits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False)
    recipient_type = Column(String, nullable=False)  # "vendor" or "platform"
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    amount = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="pending")
    paystack_split_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    payment = relationship("Payment", back_populates="splits")


class PaymentWebhook(Base):
    __tablename__ = "payment_webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    event_type = Column(String, nullable=False)
    paystack_reference = Column(String, nullable=False)
    webhook_data = Column(Text, nullable=False)  # JSON data from webhook
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    payment = relationship("Payment", back_populates="webhooks")
