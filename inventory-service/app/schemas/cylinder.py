from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import CylinderSize
from app.models.cylinder import CylinderLifecycleState, CylinderCondition, MaintenanceType, QualityCheckStatus


# Base Cylinder Schemas
class CylinderBase(BaseModel):
    """Base cylinder schema."""
    serial_number: str = Field(..., min_length=3, max_length=100)
    manufacturer_serial: Optional[str] = Field(None, max_length=100)
    cylinder_size: CylinderSize
    capacity_liters: Decimal = Field(..., gt=0)
    working_pressure_bar: Decimal = Field(..., gt=0)
    test_pressure_bar: Decimal = Field(..., gt=0)
    tare_weight_kg: Decimal = Field(..., gt=0)
    manufacturer: str = Field(..., min_length=2, max_length=255)
    manufacture_date: datetime
    material: str = Field("steel", max_length=100)
    valve_type: str = Field(..., max_length=100)
    thread_type: str = Field(..., max_length=50)
    gas_type: str = Field("medical_oxygen", max_length=50)
    purity_percentage: Decimal = Field(Decimal("99.5"), ge=0, le=100)


class CylinderCreate(CylinderBase):
    """Schema for creating a new cylinder."""
    inventory_location_id: str = Field(..., description="Inventory location ID")
    certification_number: Optional[str] = Field(None, max_length=100)
    regulatory_compliance: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class CylinderUpdate(BaseModel):
    """Schema for updating cylinder information."""
    inventory_location_id: Optional[str] = None
    lifecycle_state: Optional[CylinderLifecycleState] = None
    condition: Optional[CylinderCondition] = None
    current_pressure_bar: Optional[Decimal] = Field(None, ge=0)
    fill_level_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    current_hospital_id: Optional[str] = None
    current_order_id: Optional[str] = None
    last_known_latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    last_known_longitude: Optional[Decimal] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None
    requires_maintenance: Optional[bool] = None
    is_emergency_ready: Optional[bool] = None
    notes: Optional[str] = None


class CylinderResponse(CylinderBase):
    """Schema for cylinder response."""
    id: str
    vendor_id: str
    inventory_location_id: str
    lifecycle_state: CylinderLifecycleState
    condition: CylinderCondition
    current_pressure_bar: Decimal
    fill_level_percentage: Decimal
    current_hospital_id: Optional[str] = None
    current_order_id: Optional[str] = None
    last_known_latitude: Optional[Decimal] = None
    last_known_longitude: Optional[Decimal] = None
    last_inspection_date: Optional[datetime] = None
    next_inspection_due: Optional[datetime] = None
    last_pressure_test_date: Optional[datetime] = None
    next_pressure_test_due: Optional[datetime] = None
    certification_number: Optional[str] = None
    total_fills: int
    total_deliveries: int
    total_usage_hours: Decimal
    average_usage_rate: Optional[Decimal] = None
    is_active: bool
    is_available: bool
    requires_maintenance: bool
    is_emergency_ready: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_filled_at: Optional[datetime] = None
    last_delivered_at: Optional[datetime] = None
    last_returned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Maintenance Schemas
class CylinderMaintenanceBase(BaseModel):
    """Base maintenance schema."""
    maintenance_type: MaintenanceType
    scheduled_date: datetime
    work_description: str = Field(..., min_length=10)
    is_emergency: bool = False


class CylinderMaintenanceCreate(CylinderMaintenanceBase):
    """Schema for creating maintenance record."""
    cylinder_id: str = Field(..., description="Cylinder ID")
    technician_id: Optional[str] = None
    estimated_cost: Optional[Decimal] = Field(None, ge=0)
    estimated_hours: Optional[Decimal] = Field(None, gt=0)


class CylinderMaintenanceUpdate(BaseModel):
    """Schema for updating maintenance record."""
    completed_date: Optional[datetime] = None
    technician_id: Optional[str] = None
    work_description: Optional[str] = Field(None, min_length=10)
    parts_replaced: Optional[List[Dict[str, Any]]] = None
    labor_hours: Optional[Decimal] = Field(None, gt=0)
    cost_amount: Optional[Decimal] = Field(None, ge=0)
    post_maintenance_condition: Optional[CylinderCondition] = None
    issues_found: Optional[List[str]] = None
    recommendations: Optional[str] = None
    certification_issued: Optional[bool] = None
    certificate_number: Optional[str] = None
    certificate_expiry: Optional[datetime] = None
    is_completed: Optional[bool] = None
    next_maintenance_due: Optional[datetime] = None


class CylinderMaintenanceResponse(CylinderMaintenanceBase):
    """Schema for maintenance response."""
    id: str
    cylinder_id: str
    vendor_id: str
    completed_date: Optional[datetime] = None
    technician_id: Optional[str] = None
    parts_replaced: Optional[List[Dict[str, Any]]] = None
    labor_hours: Optional[Decimal] = None
    cost_amount: Optional[Decimal] = None
    cost_currency: str
    pre_maintenance_condition: CylinderCondition
    post_maintenance_condition: CylinderCondition
    issues_found: Optional[List[str]] = None
    recommendations: Optional[str] = None
    compliance_standards: Optional[List[str]] = None
    certification_issued: bool
    certificate_number: Optional[str] = None
    certificate_expiry: Optional[datetime] = None
    is_completed: bool
    next_maintenance_due: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Quality Check Schemas
class CylinderQualityCheckBase(BaseModel):
    """Base quality check schema."""
    check_type: str = Field(..., min_length=2, max_length=100)
    parameters_checked: Dict[str, Any] = Field(..., description="Parameters that were checked")
    measurements: Dict[str, Any] = Field(..., description="Actual measurements taken")
    acceptable_ranges: Dict[str, Any] = Field(..., description="Expected acceptable ranges")


class CylinderQualityCheckCreate(CylinderQualityCheckBase):
    """Schema for creating quality check."""
    cylinder_id: str = Field(..., description="Cylinder ID")
    inspector_id: Optional[str] = None
    regulatory_standards: Optional[List[str]] = None


class CylinderQualityCheckUpdate(BaseModel):
    """Schema for updating quality check."""
    overall_status: Optional[QualityCheckStatus] = None
    passed_checks: Optional[List[str]] = None
    failed_checks: Optional[List[str]] = None
    corrective_actions: Optional[List[str]] = None
    recommendations: Optional[str] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[datetime] = None
    compliance_status: Optional[str] = None


class CylinderQualityCheckResponse(CylinderQualityCheckBase):
    """Schema for quality check response."""
    id: str
    cylinder_id: str
    vendor_id: str
    check_date: datetime
    inspector_id: Optional[str] = None
    overall_status: QualityCheckStatus
    passed_checks: Optional[List[str]] = None
    failed_checks: Optional[List[str]] = None
    corrective_actions: Optional[List[str]] = None
    recommendations: Optional[str] = None
    follow_up_required: bool
    follow_up_date: Optional[datetime] = None
    regulatory_standards: Optional[List[str]] = None
    compliance_status: str
    created_at: datetime

    class Config:
        from_attributes = True


# Lifecycle Event Schemas
class CylinderLifecycleEventCreate(BaseModel):
    """Schema for creating lifecycle event."""
    cylinder_id: str = Field(..., description="Cylinder ID")
    event_type: str = Field(..., min_length=2, max_length=100)
    new_state: CylinderLifecycleState
    previous_state: Optional[CylinderLifecycleState] = None
    new_location_id: Optional[str] = None
    previous_location_id: Optional[str] = None
    order_id: Optional[str] = None
    hospital_id: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)


class CylinderLifecycleEventResponse(BaseModel):
    """Schema for lifecycle event response."""
    id: str
    cylinder_id: str
    event_type: str
    event_date: datetime
    triggered_by: Optional[str] = None
    previous_state: Optional[CylinderLifecycleState] = None
    new_state: CylinderLifecycleState
    previous_location_id: Optional[str] = None
    new_location_id: Optional[str] = None
    order_id: Optional[str] = None
    hospital_id: Optional[str] = None
    vendor_id: str
    event_data: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Usage Log Schemas
class CylinderUsageLogCreate(BaseModel):
    """Schema for creating usage log."""
    cylinder_id: str = Field(..., description="Cylinder ID")
    hospital_id: str = Field(..., description="Hospital ID")
    order_id: Optional[str] = None
    initial_pressure_bar: Decimal = Field(..., ge=0)
    initial_fill_percentage: Decimal = Field(..., ge=0, le=100)
    usage_type: str = Field(..., min_length=2, max_length=100)
    department: Optional[str] = Field(None, max_length=100)
    patient_count: Optional[int] = Field(None, ge=0)


class CylinderUsageLogUpdate(BaseModel):
    """Schema for updating usage log."""
    session_end: Optional[datetime] = None
    final_pressure_bar: Optional[Decimal] = Field(None, ge=0)
    final_fill_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    gas_consumed_liters: Optional[Decimal] = Field(None, ge=0)
    flow_rate_lpm: Optional[Decimal] = Field(None, gt=0)
    efficiency_rating: Optional[Decimal] = Field(None, ge=0, le=1)
    ambient_temperature: Optional[Decimal] = None
    ambient_pressure: Optional[Decimal] = Field(None, gt=0)


class CylinderUsageLogResponse(BaseModel):
    """Schema for usage log response."""
    id: str
    cylinder_id: str
    session_start: datetime
    session_end: Optional[datetime] = None
    hospital_id: str
    order_id: Optional[str] = None
    initial_pressure_bar: Decimal
    final_pressure_bar: Optional[Decimal] = None
    initial_fill_percentage: Decimal
    final_fill_percentage: Optional[Decimal] = None
    gas_consumed_liters: Optional[Decimal] = None
    usage_type: str
    department: Optional[str] = None
    patient_count: Optional[int] = None
    flow_rate_lpm: Optional[Decimal] = None
    efficiency_rating: Optional[Decimal] = None
    ambient_temperature: Optional[Decimal] = None
    ambient_pressure: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Search and Filter Schemas
class CylinderSearchFilters(BaseModel):
    """Schema for cylinder search filters."""
    vendor_id: Optional[str] = None
    inventory_location_id: Optional[str] = None
    cylinder_size: Optional[CylinderSize] = None
    lifecycle_state: Optional[CylinderLifecycleState] = None
    condition: Optional[CylinderCondition] = None
    is_available: Optional[bool] = None
    requires_maintenance: Optional[bool] = None
    is_emergency_ready: Optional[bool] = None
    current_hospital_id: Optional[str] = None
    manufacturer: Optional[str] = None
    gas_type: Optional[str] = None
    min_pressure: Optional[Decimal] = Field(None, ge=0)
    max_pressure: Optional[Decimal] = Field(None, ge=0)
    min_fill_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    max_fill_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    inspection_due_before: Optional[datetime] = None
    pressure_test_due_before: Optional[datetime] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class CylinderSearchRequest(BaseModel):
    """Schema for cylinder search request."""
    filters: CylinderSearchFilters = CylinderSearchFilters()
    sort_by: str = Field("created_at", pattern="^(created_at|serial_number|lifecycle_state|condition|last_inspection_date|next_inspection_due)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    include_maintenance_history: bool = False
    include_quality_checks: bool = False
    include_usage_logs: bool = False


class CylinderSearchResponse(BaseModel):
    """Schema for cylinder search response."""
    cylinders: List[CylinderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: CylinderSearchFilters


# Batch Operation Schemas
class CylinderBatchBase(BaseModel):
    """Base batch schema."""
    batch_number: str = Field(..., min_length=3, max_length=100)
    batch_type: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    priority: str = Field("normal", pattern="^(low|normal|high|urgent)$")
    scheduled_date: Optional[datetime] = None


class CylinderBatchCreate(CylinderBatchBase):
    """Schema for creating cylinder batch."""
    cylinder_ids: List[str] = Field(..., min_items=1, max_items=1000)
    assigned_to: Optional[str] = None
    team_members: Optional[List[str]] = None


class CylinderBatchUpdate(BaseModel):
    """Schema for updating cylinder batch."""
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|normal|high|urgent)$")
    scheduled_date: Optional[datetime] = None
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    team_members: Optional[List[str]] = None


class CylinderBatchResponse(CylinderBatchBase):
    """Schema for batch response."""
    id: str
    vendor_id: str
    total_cylinders: int
    processed_cylinders: int
    status: str
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    team_members: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Analytics and Reporting Schemas
class CylinderAnalyticsRequest(BaseModel):
    """Schema for cylinder analytics request."""
    vendor_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    group_by: str = Field("day", pattern="^(hour|day|week|month)$")
    metrics: List[str] = Field(default=["utilization", "maintenance", "quality"],
                              description="Metrics to include: utilization, maintenance, quality, lifecycle, location")


class CylinderUtilizationMetrics(BaseModel):
    """Schema for cylinder utilization metrics."""
    total_cylinders: int
    active_cylinders: int
    in_use_cylinders: int
    available_cylinders: int
    maintenance_cylinders: int
    utilization_rate: Decimal
    average_usage_hours: Decimal
    total_deliveries: int
    total_fills: int


class CylinderMaintenanceMetrics(BaseModel):
    """Schema for cylinder maintenance metrics."""
    scheduled_maintenance: int
    completed_maintenance: int
    overdue_maintenance: int
    emergency_repairs: int
    average_maintenance_cost: Decimal
    average_maintenance_time: Decimal
    compliance_rate: Decimal


class CylinderQualityMetrics(BaseModel):
    """Schema for cylinder quality metrics."""
    total_quality_checks: int
    passed_checks: int
    failed_checks: int
    quality_pass_rate: Decimal
    average_check_frequency: Decimal
    compliance_violations: int


class CylinderAnalyticsResponse(BaseModel):
    """Schema for cylinder analytics response."""
    period_start: datetime
    period_end: datetime
    vendor_id: Optional[str] = None
    utilization_metrics: Optional[CylinderUtilizationMetrics] = None
    maintenance_metrics: Optional[CylinderMaintenanceMetrics] = None
    quality_metrics: Optional[CylinderQualityMetrics] = None
    time_series_data: Optional[List[Dict[str, Any]]] = None


# Allocation and Assignment Schemas
class CylinderAllocationRequest(BaseModel):
    """Schema for cylinder allocation request."""
    order_id: str = Field(..., description="Order ID requiring cylinders")
    hospital_id: str = Field(..., description="Hospital ID")
    cylinder_size: CylinderSize
    quantity: int = Field(..., ge=1, le=100)
    delivery_latitude: Decimal = Field(..., ge=-90, le=90)
    delivery_longitude: Decimal = Field(..., ge=-180, le=180)
    is_emergency: bool = False
    preferred_vendor_id: Optional[str] = None
    max_distance_km: Decimal = Field(Decimal("50.0"), gt=0, le=200)
    min_fill_percentage: Decimal = Field(Decimal("90.0"), ge=0, le=100)
    quality_requirements: Optional[List[str]] = None


class CylinderAllocationOption(BaseModel):
    """Schema for cylinder allocation option."""
    vendor_id: str
    vendor_name: str
    inventory_location_id: str
    location_name: str
    distance_km: Decimal
    available_cylinders: List[str]  # List of cylinder IDs
    estimated_delivery_time: int  # minutes
    total_cost: Decimal
    currency: str


class CylinderAllocationResponse(BaseModel):
    """Schema for cylinder allocation response."""
    order_id: str
    allocation_options: List[CylinderAllocationOption]
    recommended_option: Optional[CylinderAllocationOption] = None
    total_options_found: int
    search_criteria: CylinderAllocationRequest
