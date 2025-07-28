from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Enum as SQLEnum, DECIMAL, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import CylinderSize


class CylinderLifecycleState(str, Enum):
    """Cylinder lifecycle states."""
    NEW = "new"
    ACTIVE = "active"
    IN_USE = "in_use"
    RETURNED = "returned"
    MAINTENANCE = "maintenance"
    INSPECTION = "inspection"
    REPAIR = "repair"
    QUARANTINE = "quarantine"
    RETIRED = "retired"
    DISPOSED = "disposed"


class CylinderCondition(str, Enum):
    """Cylinder physical condition."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    DAMAGED = "damaged"
    UNSAFE = "unsafe"


class MaintenanceType(str, Enum):
    """Types of maintenance operations."""
    ROUTINE_INSPECTION = "routine_inspection"
    PRESSURE_TEST = "pressure_test"
    VALVE_REPLACEMENT = "valve_replacement"
    CLEANING = "cleaning"
    REPAIR = "repair"
    CERTIFICATION = "certification"
    EMERGENCY_REPAIR = "emergency_repair"


class QualityCheckStatus(str, Enum):
    """Quality check results."""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    REQUIRES_ATTENTION = "requires_attention"


class Cylinder(Base):
    """Individual cylinder tracking entity."""
    __tablename__ = "cylinders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic cylinder information
    serial_number = Column(String(100), nullable=False, unique=True, index=True)
    manufacturer_serial = Column(String(100), nullable=True, index=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    inventory_location_id = Column(UUID(as_uuid=True), ForeignKey("inventory_locations.id"), nullable=False, index=True)
    
    # Physical specifications
    cylinder_size = Column(SQLEnum(CylinderSize), nullable=False, index=True)
    capacity_liters = Column(DECIMAL(8, 2), nullable=False)
    working_pressure_bar = Column(DECIMAL(8, 2), nullable=False)
    test_pressure_bar = Column(DECIMAL(8, 2), nullable=False)
    tare_weight_kg = Column(DECIMAL(8, 2), nullable=False)
    
    # Manufacturing details
    manufacturer = Column(String(255), nullable=False)
    manufacture_date = Column(DateTime(timezone=True), nullable=False)
    material = Column(String(100), nullable=False, default="steel")
    valve_type = Column(String(100), nullable=False)
    thread_type = Column(String(50), nullable=False)
    
    # Gas specifications
    gas_type = Column(String(50), nullable=False, default="medical_oxygen")
    purity_percentage = Column(DECIMAL(5, 2), nullable=False, default=99.5)
    
    # Current state
    lifecycle_state = Column(SQLEnum(CylinderLifecycleState), nullable=False, default=CylinderLifecycleState.NEW, index=True)
    condition = Column(SQLEnum(CylinderCondition), nullable=False, default=CylinderCondition.EXCELLENT, index=True)
    current_pressure_bar = Column(DECIMAL(8, 2), nullable=False, default=0.0)
    fill_level_percentage = Column(DECIMAL(5, 2), nullable=False, default=0.0)
    
    # Location and assignment tracking
    current_hospital_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    current_order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    last_known_latitude = Column(DECIMAL(10, 8), nullable=True)
    last_known_longitude = Column(DECIMAL(11, 8), nullable=True)
    
    # Compliance and certification
    last_inspection_date = Column(DateTime(timezone=True), nullable=True)
    next_inspection_due = Column(DateTime(timezone=True), nullable=True, index=True)
    last_pressure_test_date = Column(DateTime(timezone=True), nullable=True)
    next_pressure_test_due = Column(DateTime(timezone=True), nullable=True, index=True)
    certification_number = Column(String(100), nullable=True)
    regulatory_compliance = Column(JSONB, nullable=True)  # Compliance certificates and standards
    
    # Operational metrics
    total_fills = Column(Integer, nullable=False, default=0)
    total_deliveries = Column(Integer, nullable=False, default=0)
    total_usage_hours = Column(DECIMAL(10, 2), nullable=False, default=0.0)
    average_usage_rate = Column(DECIMAL(8, 4), nullable=True)  # Liters per hour
    
    # Status flags
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_available = Column(Boolean, nullable=False, default=True, index=True)
    requires_maintenance = Column(Boolean, nullable=False, default=False, index=True)
    is_emergency_ready = Column(Boolean, nullable=False, default=True, index=True)
    
    # Metadata and notes
    cylinder_metadata = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_filled_at = Column(DateTime(timezone=True), nullable=True)
    last_delivered_at = Column(DateTime(timezone=True), nullable=True)
    last_returned_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    inventory_location = relationship("Inventory", back_populates="cylinders")
    maintenance_records = relationship("CylinderMaintenance", back_populates="cylinder", cascade="all, delete-orphan")
    quality_checks = relationship("CylinderQualityCheck", back_populates="cylinder", cascade="all, delete-orphan")
    lifecycle_events = relationship("CylinderLifecycleEvent", back_populates="cylinder", cascade="all, delete-orphan")
    usage_logs = relationship("CylinderUsageLog", back_populates="cylinder", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Cylinder(id={self.id}, serial={self.serial_number}, state={self.lifecycle_state})>"


class CylinderMaintenance(Base):
    """Cylinder maintenance and service records."""
    __tablename__ = "cylinder_maintenance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cylinder_id = Column(UUID(as_uuid=True), ForeignKey("cylinders.id"), nullable=False, index=True)
    
    # Maintenance details
    maintenance_type = Column(SQLEnum(MaintenanceType), nullable=False, index=True)
    scheduled_date = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_date = Column(DateTime(timezone=True), nullable=True)
    technician_id = Column(UUID(as_uuid=True), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Work performed
    work_description = Column(Text, nullable=False)
    parts_replaced = Column(JSONB, nullable=True)  # List of replaced parts
    labor_hours = Column(DECIMAL(5, 2), nullable=True)
    cost_amount = Column(DECIMAL(10, 2), nullable=True)
    cost_currency = Column(String(3), nullable=False, default="NGN")
    
    # Results and findings
    pre_maintenance_condition = Column(SQLEnum(CylinderCondition), nullable=False)
    post_maintenance_condition = Column(SQLEnum(CylinderCondition), nullable=False)
    issues_found = Column(JSONB, nullable=True)  # List of issues discovered
    recommendations = Column(Text, nullable=True)
    
    # Compliance and certification
    compliance_standards = Column(JSONB, nullable=True)
    certification_issued = Column(Boolean, nullable=False, default=False)
    certificate_number = Column(String(100), nullable=True)
    certificate_expiry = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    is_completed = Column(Boolean, nullable=False, default=False, index=True)
    is_emergency = Column(Boolean, nullable=False, default=False)
    next_maintenance_due = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Metadata
    maintenance_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    cylinder = relationship("Cylinder", back_populates="maintenance_records")

    def __repr__(self):
        return f"<CylinderMaintenance(id={self.id}, cylinder_id={self.cylinder_id}, type={self.maintenance_type})>"


class CylinderQualityCheck(Base):
    """Quality control and safety compliance checks."""
    __tablename__ = "cylinder_quality_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cylinder_id = Column(UUID(as_uuid=True), ForeignKey("cylinders.id"), nullable=False, index=True)
    
    # Check details
    check_type = Column(String(100), nullable=False, index=True)  # visual, pressure, leak, purity, etc.
    check_date = Column(DateTime(timezone=True), nullable=False, index=True)
    inspector_id = Column(UUID(as_uuid=True), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Check parameters and results
    parameters_checked = Column(JSONB, nullable=False)  # What was checked
    measurements = Column(JSONB, nullable=False)  # Actual measurements
    acceptable_ranges = Column(JSONB, nullable=False)  # Expected ranges
    
    # Results
    overall_status = Column(SQLEnum(QualityCheckStatus), nullable=False, index=True)
    passed_checks = Column(JSONB, nullable=True)  # List of passed checks
    failed_checks = Column(JSONB, nullable=True)  # List of failed checks
    
    # Actions and recommendations
    corrective_actions = Column(JSONB, nullable=True)
    recommendations = Column(Text, nullable=True)
    follow_up_required = Column(Boolean, nullable=False, default=False)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    
    # Compliance
    regulatory_standards = Column(JSONB, nullable=True)
    compliance_status = Column(String(50), nullable=False, default="compliant")
    
    # Metadata
    quality_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    cylinder = relationship("Cylinder", back_populates="quality_checks")

    def __repr__(self):
        return f"<CylinderQualityCheck(id={self.id}, cylinder_id={self.cylinder_id}, status={self.overall_status})>"


class CylinderLifecycleEvent(Base):
    """Track all lifecycle events and state changes."""
    __tablename__ = "cylinder_lifecycle_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cylinder_id = Column(UUID(as_uuid=True), ForeignKey("cylinders.id"), nullable=False, index=True)

    # Event details
    event_type = Column(String(100), nullable=False, index=True)  # filled, delivered, returned, maintenance, etc.
    event_date = Column(DateTime(timezone=True), nullable=False, index=True)
    triggered_by = Column(UUID(as_uuid=True), nullable=True)  # User who triggered the event

    # State changes
    previous_state = Column(SQLEnum(CylinderLifecycleState), nullable=True)
    new_state = Column(SQLEnum(CylinderLifecycleState), nullable=False)
    previous_location_id = Column(UUID(as_uuid=True), nullable=True)
    new_location_id = Column(UUID(as_uuid=True), nullable=True)

    # Event context
    order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    hospital_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Event data
    event_data = Column(JSONB, nullable=True)  # Additional event-specific data
    notes = Column(Text, nullable=True)

    # Location tracking
    latitude = Column(DECIMAL(10, 8), nullable=True)
    longitude = Column(DECIMAL(11, 8), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    cylinder = relationship("Cylinder", back_populates="lifecycle_events")

    def __repr__(self):
        return f"<CylinderLifecycleEvent(id={self.id}, cylinder_id={self.cylinder_id}, event={self.event_type})>"


class CylinderUsageLog(Base):
    """Track cylinder usage patterns and consumption."""
    __tablename__ = "cylinder_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cylinder_id = Column(UUID(as_uuid=True), ForeignKey("cylinders.id"), nullable=False, index=True)

    # Usage session
    session_start = Column(DateTime(timezone=True), nullable=False, index=True)
    session_end = Column(DateTime(timezone=True), nullable=True)
    hospital_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Usage measurements
    initial_pressure_bar = Column(DECIMAL(8, 2), nullable=False)
    final_pressure_bar = Column(DECIMAL(8, 2), nullable=True)
    initial_fill_percentage = Column(DECIMAL(5, 2), nullable=False)
    final_fill_percentage = Column(DECIMAL(5, 2), nullable=True)
    gas_consumed_liters = Column(DECIMAL(10, 2), nullable=True)

    # Usage context
    usage_type = Column(String(100), nullable=False, index=True)  # emergency, routine, surgery, etc.
    department = Column(String(100), nullable=True)
    patient_count = Column(Integer, nullable=True)

    # Performance metrics
    flow_rate_lpm = Column(DECIMAL(8, 2), nullable=True)  # Liters per minute
    efficiency_rating = Column(DECIMAL(3, 2), nullable=True)  # 0.0 to 1.0

    # Environmental conditions
    ambient_temperature = Column(DECIMAL(5, 2), nullable=True)
    ambient_pressure = Column(DECIMAL(8, 2), nullable=True)

    # Metadata
    usage_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    cylinder = relationship("Cylinder", back_populates="usage_logs")

    def __repr__(self):
        return f"<CylinderUsageLog(id={self.id}, cylinder_id={self.cylinder_id}, hospital_id={self.hospital_id})>"


class CylinderBatch(Base):
    """Group cylinders for batch operations and tracking."""
    __tablename__ = "cylinder_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Batch information
    batch_number = Column(String(100), nullable=False, unique=True, index=True)
    batch_type = Column(String(50), nullable=False, index=True)  # delivery, maintenance, inspection, etc.
    vendor_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Batch details
    description = Column(Text, nullable=True)
    total_cylinders = Column(Integer, nullable=False, default=0)
    processed_cylinders = Column(Integer, nullable=False, default=0)

    # Status
    status = Column(String(50), nullable=False, default="pending", index=True)
    priority = Column(String(20), nullable=False, default="normal")

    # Scheduling
    scheduled_date = Column(DateTime(timezone=True), nullable=True, index=True)
    started_date = Column(DateTime(timezone=True), nullable=True)
    completed_date = Column(DateTime(timezone=True), nullable=True)

    # Assignment
    assigned_to = Column(UUID(as_uuid=True), nullable=True)
    team_members = Column(JSONB, nullable=True)  # List of team member IDs

    # Metadata
    batch_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CylinderBatch(id={self.id}, batch_number={self.batch_number}, status={self.status})>"


class CylinderBatchItem(Base):
    """Individual cylinders within a batch."""
    __tablename__ = "cylinder_batch_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("cylinder_batches.id"), nullable=False, index=True)
    cylinder_id = Column(UUID(as_uuid=True), ForeignKey("cylinders.id"), nullable=False, index=True)

    # Item status
    status = Column(String(50), nullable=False, default="pending", index=True)
    sequence_number = Column(Integer, nullable=False)

    # Processing details
    processed_date = Column(DateTime(timezone=True), nullable=True)
    processed_by = Column(UUID(as_uuid=True), nullable=True)
    processing_notes = Column(Text, nullable=True)

    # Results
    result_status = Column(String(50), nullable=True)
    result_data = Column(JSONB, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    batch = relationship("CylinderBatch")
    cylinder = relationship("Cylinder")

    def __repr__(self):
        return f"<CylinderBatchItem(id={self.id}, batch_id={self.batch_id}, cylinder_id={self.cylinder_id})>"
