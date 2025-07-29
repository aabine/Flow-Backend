from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum, Integer, Float, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import sys
import os
from enum import Enum as PyEnum

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import UserRole


class AdminActionType(str, PyEnum):
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_SUSPENDED = "user_suspended"
    USER_ACTIVATED = "user_activated"
    ORDER_CANCELLED = "order_cancelled"
    REVIEW_MODERATED = "review_moderated"
    SUPPLIER_APPROVED = "supplier_approved"
    SUPPLIER_REJECTED = "supplier_rejected"
    SYSTEM_CONFIG_UPDATED = "system_config_updated"
    BULK_ACTION_PERFORMED = "bulk_action_performed"


class MetricType(str, PyEnum):
    ORDER_COUNT = "order_count"
    REVENUE = "revenue"
    USER_COUNT = "user_count"
    REVIEW_COUNT = "review_count"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    ACTIVE_SESSIONS = "active_sessions"


class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)  # Reference to main users table
    
    # Admin specific fields
    admin_level = Column(String, default="admin")  # admin
    permissions = Column(JSON, default=list)  # List of specific permissions
    
    # Access control
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    login_count = Column(Integer, default=0)
    
    # Session management
    current_session_id = Column(String, nullable=True)
    session_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    audit_logs = relationship("AuditLog", back_populates="admin_user")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey('admin_users.id'), nullable=False, index=True)
    
    # Action details
    action_type = Column(Enum(AdminActionType), nullable=False, index=True)
    resource_type = Column(String, nullable=False)  # user, order, review, etc.
    resource_id = Column(String, nullable=True, index=True)
    
    # Action context
    description = Column(Text, nullable=False)
    old_values = Column(JSON, nullable=True)  # Previous state
    new_values = Column(JSON, nullable=True)  # New state
    
    # Request context
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    request_id = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    admin_user = relationship("AdminUser", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_log_action_date', 'action_type', 'created_at'),
        Index('idx_audit_log_resource', 'resource_type', 'resource_id'),
    )


class SystemMetrics(Base):
    __tablename__ = "system_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Metric identification
    metric_type = Column(Enum(MetricType), nullable=False, index=True)
    service_name = Column(String, nullable=False, index=True)
    
    # Metric data
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=True)  # count, percentage, milliseconds, etc.
    
    # Metadata
    metric_metadata = Column(JSON, nullable=True)  # Additional context data
    tags = Column(JSON, nullable=True)  # For filtering and grouping
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_system_metrics_type_time', 'metric_type', 'timestamp'),
        Index('idx_system_metrics_service_time', 'service_name', 'timestamp'),
    )


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    admin_user_id = Column(UUID(as_uuid=True), ForeignKey('admin_users.id'), nullable=False, index=True)
    
    # Widget configuration
    widget_type = Column(String, nullable=False)  # chart, metric, table, etc.
    title = Column(String, nullable=False)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    width = Column(Integer, default=4)
    height = Column(Integer, default=3)
    
    # Widget settings
    config = Column(JSON, nullable=True)  # Chart config, filters, etc.
    data_source = Column(String, nullable=False)  # API endpoint or query
    refresh_interval = Column(Integer, default=300)  # seconds
    
    # State
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SystemAlert(Base):
    __tablename__ = "system_alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Alert details
    alert_type = Column(String, nullable=False, index=True)  # error, warning, info
    severity = Column(String, nullable=False, index=True)  # low, medium, high, critical
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    
    # Source information
    service_name = Column(String, nullable=False, index=True)
    component = Column(String, nullable=True)
    
    # Alert data
    details = Column(JSON, nullable=True)  # Additional context
    threshold_value = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    
    # State management
    status = Column(String, default="active", index=True)  # active, acknowledged, resolved
    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_system_alerts_status_severity', 'status', 'severity'),
        Index('idx_system_alerts_service_time', 'service_name', 'created_at'),
    )
