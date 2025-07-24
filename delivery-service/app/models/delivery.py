from sqlalchemy import Column, String, Float, DateTime, Boolean, Text, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid
import enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import CylinderSize

Base = declarative_base()


class DeliveryStatus(enum.Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeliveryPriority(enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class DriverStatus(enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFF_DUTY = "OFF_DUTY"
    UNAVAILABLE = "UNAVAILABLE"


class VehicleType(enum.Enum):
    MOTORCYCLE = "MOTORCYCLE"
    CAR = "CAR"
    VAN = "VAN"
    TRUCK = "TRUCK"


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, unique=True)  # Reference to user service
    driver_license = Column(String, nullable=False, unique=True)
    phone_number = Column(String, nullable=False)
    vehicle_type = Column(Enum(VehicleType), nullable=False)
    vehicle_plate = Column(String, nullable=False)
    vehicle_capacity = Column(Integer, nullable=False)  # Number of cylinders
    current_location_lat = Column(Float, nullable=True)
    current_location_lng = Column(Float, nullable=True)
    status = Column(Enum(DriverStatus), default=DriverStatus.AVAILABLE)
    rating = Column(Float, default=5.0)
    total_deliveries = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    deliveries = relationship("Delivery", back_populates="driver")
    routes = relationship("DeliveryRoute", back_populates="driver")


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String, nullable=False, unique=True)  # Reference to order service
    customer_id = Column(String, nullable=False)  # Reference to user service
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=True)
    
    # Delivery details
    cylinder_size = Column(Enum(CylinderSize), nullable=False)
    quantity = Column(Integer, nullable=False)
    priority = Column(Enum(DeliveryPriority), default=DeliveryPriority.NORMAL)
    status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    
    # Addresses
    pickup_address = Column(Text, nullable=False)
    pickup_lat = Column(Float, nullable=False)
    pickup_lng = Column(Float, nullable=False)
    delivery_address = Column(Text, nullable=False)
    delivery_lat = Column(Float, nullable=False)
    delivery_lng = Column(Float, nullable=False)
    
    # Timing
    requested_delivery_time = Column(DateTime, nullable=True)
    estimated_pickup_time = Column(DateTime, nullable=True)
    estimated_delivery_time = Column(DateTime, nullable=True)
    actual_pickup_time = Column(DateTime, nullable=True)
    actual_delivery_time = Column(DateTime, nullable=True)
    
    # Distance and cost
    distance_km = Column(Float, nullable=True)
    delivery_fee = Column(Float, nullable=False)
    
    # Additional info
    special_instructions = Column(Text, nullable=True)
    delivery_notes = Column(Text, nullable=True)
    customer_signature = Column(String, nullable=True)  # Base64 encoded signature
    delivery_photo = Column(String, nullable=True)  # Photo URL
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    driver = relationship("Driver", back_populates="deliveries")
    tracking_updates = relationship("DeliveryTracking", back_populates="delivery", cascade="all, delete-orphan")


class DeliveryTracking(Base):
    __tablename__ = "delivery_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delivery_id = Column(UUID(as_uuid=True), ForeignKey("deliveries.id"), nullable=False)
    status = Column(Enum(DeliveryStatus), nullable=False)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String, nullable=False)  # User ID who created the update

    # Relationships
    delivery = relationship("Delivery", back_populates="tracking_updates")


class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)
    route_name = Column(String, nullable=False)
    delivery_ids = Column(JSONB, nullable=False)  # List of delivery IDs in order
    total_distance_km = Column(Float, nullable=False)
    estimated_duration_minutes = Column(Integer, nullable=False)
    optimized_waypoints = Column(JSONB, nullable=False)  # Optimized route coordinates
    status = Column(String, default="PLANNED")  # PLANNED, ACTIVE, COMPLETED
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    driver = relationship("Driver", back_populates="routes")
