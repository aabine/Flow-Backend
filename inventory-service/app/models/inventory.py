from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import CylinderSize, CylinderStatus


class Inventory(Base):
    __tablename__ = "inventory_locations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vendor_id = Column(String, nullable=False, index=True)
    location_name = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    country = Column(String, nullable=False, default="Nigeria")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    stock = relationship("CylinderStock", back_populates="inventory", cascade="all, delete-orphan")
    movements = relationship("StockMovement", back_populates="inventory", cascade="all, delete-orphan")


class CylinderStock(Base):
    __tablename__ = "cylinder_stock"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    inventory_id = Column(String, ForeignKey("inventory_locations.id"), nullable=False)
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    total_quantity = Column(Integer, nullable=False, default=0)
    available_quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    minimum_threshold = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    inventory = relationship("Inventory", back_populates="stock")
    movements = relationship("StockMovement", back_populates="stock", cascade="all, delete-orphan")
    
    # Unique constraint on inventory_id and cylinder_size
    __table_args__ = (
        {"extend_existing": True}
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    inventory_id = Column(String, ForeignKey("inventory_locations.id"), nullable=False)
    stock_id = Column(String, ForeignKey("cylinder_stock.id"), nullable=False)
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    movement_type = Column(String, nullable=False)  # 'in', 'out', 'reserved', 'released'
    quantity = Column(Integer, nullable=False)
    previous_quantity = Column(Integer, nullable=False)
    new_quantity = Column(Integer, nullable=False)
    order_id = Column(String, nullable=True)  # For order-related movements
    notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    inventory = relationship("Inventory", back_populates="movements")
    stock = relationship("CylinderStock", back_populates="movements")


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    inventory_id = Column(String, ForeignKey("inventory_locations.id"), nullable=False)
    stock_id = Column(String, ForeignKey("cylinder_stock.id"), nullable=False)
    order_id = Column(String, nullable=False, unique=True)
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    quantity = Column(Integer, nullable=False)
    reserved_by = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
