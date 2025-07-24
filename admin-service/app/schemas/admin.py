from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import UserRole
from app.models.admin import AdminActionType, MetricType


# Dashboard Schemas
class DashboardMetric(BaseModel):
    title: str
    value: Union[int, float, str]
    unit: Optional[str] = None
    change: Optional[float] = None  # Percentage change
    change_period: Optional[str] = None  # "24h", "7d", "30d"
    trend: Optional[str] = None  # "up", "down", "stable"


class DashboardKPI(BaseModel):
    total_orders: DashboardMetric
    total_revenue: DashboardMetric
    active_users: DashboardMetric
    average_rating: DashboardMetric
    platform_fee_revenue: DashboardMetric
    order_completion_rate: DashboardMetric


class ChartDataPoint(BaseModel):
    x: Union[str, datetime, float]
    y: Union[int, float]
    label: Optional[str] = None


class ChartData(BaseModel):
    labels: List[str]
    datasets: List[Dict[str, Any]]


class DashboardChart(BaseModel):
    title: str
    type: str  # line, bar, pie, doughnut
    data: ChartData
    options: Optional[Dict[str, Any]] = None


# Analytics Schemas
class OrderAnalytics(BaseModel):
    total_orders: int
    completed_orders: int
    cancelled_orders: int
    emergency_orders: int
    completion_rate: float
    average_order_value: float
    order_trends: List[ChartDataPoint]


class RevenueAnalytics(BaseModel):
    total_revenue: float
    platform_fees: float
    vendor_payouts: float
    revenue_by_period: List[ChartDataPoint]
    top_revenue_vendors: List[Dict[str, Any]]


class UserAnalytics(BaseModel):
    total_hospitals: int
    total_vendors: int
    active_users_24h: int
    new_registrations: int
    user_growth_trend: List[ChartDataPoint]
    geographic_distribution: List[Dict[str, Any]]


class ReviewAnalytics(BaseModel):
    total_reviews: int
    average_rating: float
    rating_distribution: Dict[str, int]
    flagged_reviews: int
    review_trends: List[ChartDataPoint]


class SystemAnalytics(BaseModel):
    service_health: Dict[str, str]
    response_times: Dict[str, float]
    error_rates: Dict[str, float]
    uptime_percentage: float


# User Management Schemas
class UserManagementFilter(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[str] = None  # active, suspended, pending
    registration_date_from: Optional[datetime] = None
    registration_date_to: Optional[datetime] = None
    search_term: Optional[str] = None


class UserManagementResponse(BaseModel):
    id: str
    email: str
    role: UserRole
    status: str
    registration_date: datetime
    last_login: Optional[datetime] = None
    order_count: Optional[int] = None
    total_spent: Optional[float] = None
    rating: Optional[float] = None


class UserActionRequest(BaseModel):
    action: str  # suspend, activate, delete, reset_password
    reason: Optional[str] = None
    notify_user: bool = True


# Order Management Schemas
class OrderManagementFilter(BaseModel):
    status: Optional[str] = None
    is_emergency: Optional[bool] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    hospital_id: Optional[str] = None
    vendor_id: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None


class OrderManagementResponse(BaseModel):
    id: str
    reference: str
    hospital_name: str
    vendor_name: Optional[str] = None
    status: str
    total_amount: Optional[float] = None
    is_emergency: bool
    created_at: datetime
    delivery_address: str


class OrderActionRequest(BaseModel):
    action: str  # cancel, refund, escalate
    reason: str
    notify_parties: bool = True


# Review Moderation Schemas
class ReviewModerationFilter(BaseModel):
    status: Optional[str] = None  # active, flagged, hidden
    rating: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_reports: Optional[bool] = None


class ReviewModerationResponse(BaseModel):
    id: str
    order_id: str
    reviewer_name: str
    reviewee_name: str
    rating: int
    comment: Optional[str] = None
    status: str
    report_count: int
    created_at: datetime


class ReviewModerationAction(BaseModel):
    action: str  # approve, hide, delete, flag
    reason: Optional[str] = None
    admin_notes: Optional[str] = None


# System Monitoring Schemas
class ServiceHealthStatus(BaseModel):
    service_name: str
    status: str  # healthy, degraded, down
    response_time: Optional[float] = None
    last_check: datetime
    error_message: Optional[str] = None


class SystemHealthResponse(BaseModel):
    overall_status: str
    services: List[ServiceHealthStatus]
    database_status: str
    redis_status: str
    rabbitmq_status: str


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    message: str
    service_name: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime] = None


class AlertActionRequest(BaseModel):
    action: str  # acknowledge, resolve, escalate
    notes: Optional[str] = None


# Audit Log Schemas
class AuditLogFilter(BaseModel):
    admin_user_id: Optional[str] = None
    action_type: Optional[AdminActionType] = None
    resource_type: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    id: str
    admin_user_email: str
    action_type: AdminActionType
    resource_type: str
    resource_id: Optional[str] = None
    description: str
    ip_address: Optional[str] = None
    created_at: datetime


# Export Schemas
class ExportRequest(BaseModel):
    export_type: str  # users, orders, reviews, analytics
    format: str = "csv"  # csv, xlsx, json
    filters: Optional[Dict[str, Any]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ExportResponse(BaseModel):
    export_id: str
    status: str  # pending, processing, completed, failed
    download_url: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


# Pagination
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int


# Admin User Schemas
class AdminUserCreate(BaseModel):
    user_id: str
    admin_level: str = "admin"
    permissions: List[str] = []


class AdminUserResponse(BaseModel):
    id: str
    user_id: str
    admin_level: str
    permissions: List[str]
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
