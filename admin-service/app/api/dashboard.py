from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService
from app.services.system_monitoring_service import SystemMonitoringService
from app.schemas.admin import (
    DashboardKPI, OrderAnalytics, RevenueAnalytics, UserAnalytics,
    ReviewAnalytics, SystemAnalytics, SystemHealthResponse
)
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_admin_user

router = APIRouter()
analytics_service = AnalyticsService()
monitoring_service = SystemMonitoringService()


# Using shared authentication function from shared.security.auth


@router.get("/")
async def get_admin_dashboard(
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get admin dashboard overview."""
    try:
        # Get all dashboard metrics
        dashboard_data = {
            "overview": {
                "message": "Admin Dashboard - Main overview endpoint",
                "status": "operational",
                "timestamp": "2025-07-27T12:00:00Z"
            },
            "quick_stats": {
                "total_users": "Available via /kpis endpoint",
                "total_orders": "Available via /kpis endpoint",
                "total_revenue": "Available via /kpis endpoint",
                "system_health": "Available via /system-health endpoint"
            },
            "available_endpoints": {
                "kpis": "/admin/dashboard/kpis",
                "system_health": "/admin/dashboard/system-health",
                "orders": "/admin/dashboard/orders",
                "users": "/admin/dashboard/users",
                "revenue": "/admin/dashboard/revenue"
            }
        }

        return {
            "success": True,
            "message": "Dashboard data retrieved successfully",
            "data": dashboard_data
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard data: {str(e)}"
        )


@router.get("/kpis", response_model=DashboardKPI)
async def get_dashboard_kpis(
    period: str = Query("30d", pattern="^(24h|7d|30d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get key performance indicators for the dashboard."""
    try:
        kpis = await analytics_service.get_dashboard_kpis(db, period)
        return kpis
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard KPIs")


@router.get("/analytics/orders", response_model=OrderAnalytics)
async def get_order_analytics(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed order analytics."""
    try:
        analytics = await analytics_service.get_order_analytics(db, period)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch order analytics")


@router.get("/analytics/revenue", response_model=RevenueAnalytics)
async def get_revenue_analytics(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed revenue analytics."""
    try:
        analytics = await analytics_service.get_revenue_analytics(db, period)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch revenue analytics")


@router.get("/analytics/users", response_model=UserAnalytics)
async def get_user_analytics(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed user analytics."""
    try:
        analytics = await analytics_service.get_user_analytics(db, period)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch user analytics")


@router.get("/analytics/reviews", response_model=ReviewAnalytics)
async def get_review_analytics(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed review analytics."""
    try:
        analytics = await analytics_service.get_review_analytics(db, period)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch review analytics")


@router.get("/analytics/system", response_model=SystemAnalytics)
async def get_system_analytics(
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system health and performance analytics."""
    try:
        analytics = await analytics_service.get_system_analytics(db)
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch system analytics")


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive system health status."""
    try:
        health = await monitoring_service.get_system_health(db)
        return health
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch system health")


@router.get("/overview")
async def get_system_overview(
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system overview with key metrics."""
    try:
        overview = await monitoring_service.get_system_overview(db)
        return overview
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch system overview")


@router.get("/metrics/{service_name}")
async def get_service_metrics(
    service_name: str,
    metric_type: str = Query(..., pattern="^(response_time|error_rate|order_count|revenue)$"),
    hours: int = Query(24, ge=1, le=168),  # 1 hour to 1 week
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get metrics for a specific service."""
    try:
        from app.models.admin import MetricType
        
        # Convert string to enum
        metric_type_enum = getattr(MetricType, metric_type.upper(), None)
        if not metric_type_enum:
            raise HTTPException(status_code=400, detail="Invalid metric type")
        
        metrics = await monitoring_service.get_service_metrics(
            db, service_name, metric_type_enum, hours
        )
        return {"service": service_name, "metric_type": metric_type, "data": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch service metrics")


@router.post("/metrics/collect", response_model=APIResponse)
async def trigger_metrics_collection(
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger system metrics collection."""
    try:
        await monitoring_service.collect_system_metrics(db)
        return APIResponse(
            success=True,
            message="Metrics collection triggered successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to trigger metrics collection")


@router.get("/charts/order-trends")
async def get_order_trends_chart(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order trends chart data."""
    try:
        analytics = await analytics_service.get_order_analytics(db, period)
        
        chart_data = {
            "title": "Order Trends",
            "type": "line",
            "data": {
                "labels": [point.x for point in analytics.order_trends],
                "datasets": [{
                    "label": "Orders",
                    "data": [point.y for point in analytics.order_trends],
                    "borderColor": "rgb(75, 192, 192)",
                    "backgroundColor": "rgba(75, 192, 192, 0.2)"
                }]
            }
        }
        
        return chart_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch order trends chart")


@router.get("/charts/revenue-breakdown")
async def get_revenue_breakdown_chart(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get revenue breakdown chart data."""
    try:
        analytics = await analytics_service.get_revenue_analytics(db, period)
        
        chart_data = {
            "title": "Revenue Breakdown",
            "type": "doughnut",
            "data": {
                "labels": ["Platform Fees", "Vendor Payouts"],
                "datasets": [{
                    "data": [analytics.platform_fees, analytics.vendor_payouts],
                    "backgroundColor": [
                        "rgba(255, 99, 132, 0.8)",
                        "rgba(54, 162, 235, 0.8)"
                    ]
                }]
            }
        }
        
        return chart_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch revenue breakdown chart")


@router.get("/charts/user-growth")
async def get_user_growth_chart(
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user growth chart data."""
    try:
        analytics = await analytics_service.get_user_analytics(db, period)
        
        chart_data = {
            "title": "User Growth",
            "type": "line",
            "data": {
                "labels": [point.x for point in analytics.user_growth_trend],
                "datasets": [{
                    "label": "New Users",
                    "data": [point.y for point in analytics.user_growth_trend],
                    "borderColor": "rgb(153, 102, 255)",
                    "backgroundColor": "rgba(153, 102, 255, 0.2)"
                }]
            }
        }
        
        return chart_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch user growth chart")
