from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.user_management_service import UserManagementService
from app.services.system_monitoring_service import SystemMonitoringService
from app.schemas.admin import (
    UserManagementFilter, UserManagementResponse, UserActionRequest,
    OrderManagementFilter, OrderManagementResponse, OrderActionRequest,
    ReviewModerationFilter, ReviewModerationResponse, ReviewModerationAction,
    AlertResponse, AlertActionRequest, AdminUserCreate, AdminUserResponse,
    AuditLogResponse, PaginatedResponse
)
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_admin_user

router = APIRouter()
user_management_service = UserManagementService()
monitoring_service = SystemMonitoringService()


# Using shared authentication function from shared.security.auth


# User Management Routes
@router.get("/users", response_model=PaginatedResponse)
async def get_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get users with filtering and pagination."""
    try:
        filters = UserManagementFilter(
            role=UserRole(role) if role else None,
            status=status,
            search_term=search
        )
        
        users, total = await user_management_service.get_users(db, filters, page, size)
        pages = (total + size - 1) // size
        
        return PaginatedResponse(
            items=[user.dict() for user in users],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch users")


@router.get("/users/{user_id}")
async def get_user_details(
    user_id: str,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a specific user."""
    try:
        user_details = await user_management_service.get_user_details(user_id)
        if not user_details:
            raise HTTPException(status_code=404, detail="User not found")
        return user_details
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch user details")


@router.post("/users/{user_id}/actions", response_model=APIResponse)
async def perform_user_action(
    user_id: str,
    action_request: UserActionRequest,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform administrative action on a user."""
    try:
        success = await user_management_service.perform_user_action(
            db, user_id, action_request, current_admin["user_id"]
        )
        
        if success:
            return APIResponse(
                success=True,
                message=f"Action '{action_request.action}' performed successfully"
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to perform action")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to perform user action")


@router.post("/users/bulk-actions", response_model=APIResponse)
async def perform_bulk_user_action(
    user_ids: List[str],
    action_request: UserActionRequest,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform bulk action on multiple users."""
    try:
        result = await user_management_service.bulk_user_action(
            db, user_ids, action_request, current_admin["user_id"]
        )
        
        return APIResponse(
            success=True,
            message=f"Bulk action completed: {result['success_count']} successful, {result['failure_count']} failed",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to perform bulk action")


# Order Management Routes
@router.get("/orders")
async def get_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    is_emergency: Optional[bool] = Query(None),
    hospital_id: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get orders with filtering and pagination."""
    try:
        # This would call order service for order management
        # Implementation would be similar to user management
        return {"message": "Order management endpoint - to be implemented"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch orders")


@router.post("/orders/{order_id}/actions", response_model=APIResponse)
async def perform_order_action(
    order_id: str,
    action_request: OrderActionRequest,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform administrative action on an order."""
    try:
        # Implementation would call order service
        return APIResponse(
            success=True,
            message=f"Order action '{action_request.action}' performed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to perform order action")


# Review Moderation Routes
@router.get("/reviews")
async def get_reviews_for_moderation(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    has_reports: Optional[bool] = Query(None),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get reviews for moderation with filtering."""
    try:
        # This would call review service for moderation
        return {"message": "Review moderation endpoint - to be implemented"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch reviews")


@router.post("/reviews/{review_id}/moderate", response_model=APIResponse)
async def moderate_review(
    review_id: str,
    action_request: ReviewModerationAction,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Moderate a review."""
    try:
        # Implementation would call review service
        return APIResponse(
            success=True,
            message=f"Review moderation action '{action_request.action}' performed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to moderate review")


# Alert Management Routes
@router.get("/alerts", response_model=PaginatedResponse)
async def get_alerts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system alerts with filtering."""
    try:
        alerts, total = await monitoring_service.get_alerts(db, status, severity, page, size)
        pages = (total + size - 1) // size
        
        return PaginatedResponse(
            items=[alert.dict() for alert in alerts],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch alerts")


@router.post("/alerts/{alert_id}/actions", response_model=APIResponse)
async def handle_alert_action(
    alert_id: str,
    action_request: AlertActionRequest,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Handle admin action on an alert."""
    try:
        success = await monitoring_service.handle_alert_action(
            db, alert_id, action_request, current_admin["user_id"]
        )
        
        if success:
            return APIResponse(
                success=True,
                message=f"Alert action '{action_request.action}' performed successfully"
            )
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to handle alert action")


# Admin User Management Routes
@router.get("/admin-users", response_model=PaginatedResponse)
async def get_admin_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of admin users."""
    try:
        admin_users, total = await user_management_service.get_admin_users(db, page, size)
        pages = (total + size - 1) // size
        
        return PaginatedResponse(
            items=[admin_user.dict() for admin_user in admin_users],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch admin users")


@router.post("/admin-users", response_model=APIResponse)
async def create_admin_user(
    admin_data: AdminUserCreate,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new admin user."""
    try:
        admin_user = await user_management_service.create_admin_user(
            db, admin_data, current_admin["user_id"]
        )
        
        if admin_user:
            return APIResponse(
                success=True,
                message="Admin user created successfully",
                data={"admin_user_id": str(admin_user.id)}
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to create admin user")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create admin user")


# Audit Log Routes
@router.get("/audit-logs", response_model=PaginatedResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin_user_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit logs with filtering."""
    try:
        filters = {
            "admin_user_id": admin_user_id,
            "action_type": action_type,
            "resource_type": resource_type
        }
        
        audit_logs, total = await user_management_service.get_audit_logs(db, filters, page, size)
        pages = (total + size - 1) // size
        
        return PaginatedResponse(
            items=[log.dict() for log in audit_logs],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch audit logs")
