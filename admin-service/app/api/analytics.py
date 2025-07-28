from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import csv
import json
import io
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.analytics_service import AnalyticsService
from app.schemas.admin import ExportRequest, ExportResponse
from shared.models import APIResponse, UserRole
from shared.security.auth import get_current_admin_user

router = APIRouter()
analytics_service = AnalyticsService()


# Using shared authentication function from shared.security.auth


@router.get("/financial-summary")
async def get_financial_summary(
    period: str = Query("30d", regex="^(7d|30d|90d|1y)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive financial summary."""
    try:
        revenue_analytics = await analytics_service.get_revenue_analytics(db, period)
        
        # Calculate additional financial metrics
        total_transactions = revenue_analytics.total_revenue / 1000 if revenue_analytics.total_revenue > 0 else 0  # Estimate
        platform_fee_rate = (revenue_analytics.platform_fees / revenue_analytics.total_revenue * 100) if revenue_analytics.total_revenue > 0 else 0
        
        financial_summary = {
            "period": period,
            "total_revenue": revenue_analytics.total_revenue,
            "platform_fees": revenue_analytics.platform_fees,
            "vendor_payouts": revenue_analytics.vendor_payouts,
            "platform_fee_rate": round(platform_fee_rate, 2),
            "estimated_transactions": int(total_transactions),
            "revenue_trends": revenue_analytics.revenue_by_period,
            "top_revenue_vendors": revenue_analytics.top_revenue_vendors,
            "generated_at": datetime.now(datetime.timezone.utc).isoformat()
        }
        
        return financial_summary
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch financial summary")


@router.get("/geographic-analytics")
async def get_geographic_analytics(
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get geographic distribution analytics."""
    try:
        user_analytics = await analytics_service.get_user_analytics(db, period)
        
        # Enhanced geographic data would come from location service
        geographic_data = {
            "period": period,
            "user_distribution": user_analytics.geographic_distribution,
            "total_locations": len(user_analytics.geographic_distribution),
            "top_cities": sorted(
                user_analytics.geographic_distribution, 
                key=lambda x: x.get("user_count", 0), 
                reverse=True
            )[:10],
            "generated_at": datetime.now(datetime.timezone.utc).isoformat()
        }
        
        return geographic_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch geographic analytics")


@router.get("/performance-metrics")
async def get_performance_metrics(
    period: str = Query("24h", regex="^(1h|24h|7d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get system performance metrics."""
    try:
        system_analytics = await analytics_service.get_system_analytics(db)
        
        performance_metrics = {
            "period": period,
            "service_health": system_analytics.service_health,
            "response_times": system_analytics.response_times,
            "error_rates": system_analytics.error_rates,
            "uptime_percentage": system_analytics.uptime_percentage,
            "average_response_time": sum(system_analytics.response_times.values()) / len(system_analytics.response_times) if system_analytics.response_times else 0,
            "services_down": sum(1 for status in system_analytics.service_health.values() if status == "down"),
            "generated_at": datetime.now(datetime.timezone.utc).isoformat()
        }
        
        return performance_metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch performance metrics")


@router.get("/business-insights")
async def get_business_insights(
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get business insights and trends."""
    try:
        # Fetch all analytics
        order_analytics = await analytics_service.get_order_analytics(db, period)
        revenue_analytics = await analytics_service.get_revenue_analytics(db, period)
        user_analytics = await analytics_service.get_user_analytics(db, period)
        review_analytics = await analytics_service.get_review_analytics(db, period)
        
        # Calculate business insights
        avg_order_value = revenue_analytics.total_revenue / order_analytics.total_orders if order_analytics.total_orders > 0 else 0
        customer_satisfaction = review_analytics.average_rating
        growth_rate = ((user_analytics.new_registrations / (user_analytics.total_hospitals + user_analytics.total_vendors)) * 100) if (user_analytics.total_hospitals + user_analytics.total_vendors) > 0 else 0
        
        insights = {
            "period": period,
            "key_metrics": {
                "average_order_value": round(avg_order_value, 2),
                "customer_satisfaction": round(customer_satisfaction, 2),
                "order_completion_rate": order_analytics.completion_rate,
                "user_growth_rate": round(growth_rate, 2),
                "emergency_order_percentage": (order_analytics.emergency_orders / order_analytics.total_orders * 100) if order_analytics.total_orders > 0 else 0
            },
            "trends": {
                "orders": order_analytics.order_trends,
                "revenue": revenue_analytics.revenue_by_period,
                "users": user_analytics.user_growth_trend,
                "reviews": review_analytics.review_trends
            },
            "recommendations": _generate_business_recommendations(
                order_analytics, revenue_analytics, user_analytics, review_analytics
            ),
            "generated_at": datetime.now(datetime.timezone.utc).isoformat()
        }
        
        return insights
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch business insights")


@router.post("/export", response_model=ExportResponse)
async def create_export(
    export_request: ExportRequest,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a data export request."""
    try:
        # Generate export ID
        export_id = f"export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{current_admin['user_id'][:8]}"
        
        # For now, return immediate response. In production, this would be async
        export_response = ExportResponse(
            export_id=export_id,
            status="completed",  # Would be "pending" for async processing
            download_url=f"/admin/analytics/download/{export_id}",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        return export_response
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create export")


@router.get("/download/{export_id}")
async def download_export(
    export_id: str,
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Download exported data."""
    try:
        # In a real implementation, you would fetch the actual export data
        # For demo purposes, we'll generate sample CSV data
        
        sample_data = [
            {"date": "2024-01-01", "orders": 150, "revenue": 75000, "users": 25},
            {"date": "2024-01-02", "orders": 180, "revenue": 90000, "users": 30},
            {"date": "2024-01-03", "orders": 165, "revenue": 82500, "users": 28},
        ]
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sample_data[0].keys())
        writer.writeheader()
        writer.writerows(sample_data)
        csv_content = output.getvalue()
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(csv_content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={export_id}.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to download export")


@router.get("/reports/monthly")
async def get_monthly_report(
    year: int = Query(..., ge=2020, le=2030),
    month: int = Query(..., ge=1, le=12),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive monthly report."""
    try:
        # Calculate date range for the month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        # Fetch analytics for the month
        order_analytics = await analytics_service.get_order_analytics(db, "30d")
        revenue_analytics = await analytics_service.get_revenue_analytics(db, "30d")
        user_analytics = await analytics_service.get_user_analytics(db, "30d")
        review_analytics = await analytics_service.get_review_analytics(db, "30d")
        
        monthly_report = {
            "report_period": f"{year}-{month:02d}",
            "summary": {
                "total_orders": order_analytics.total_orders,
                "total_revenue": revenue_analytics.total_revenue,
                "new_users": user_analytics.new_registrations,
                "average_rating": review_analytics.average_rating,
                "completion_rate": order_analytics.completion_rate
            },
            "detailed_metrics": {
                "orders": order_analytics.dict(),
                "revenue": revenue_analytics.dict(),
                "users": user_analytics.dict(),
                "reviews": review_analytics.dict()
            },
            "generated_at": datetime.now(datetime.timezone.utc).isoformat(),
            "generated_by": current_admin["user_id"]
        }
        
        return monthly_report
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate monthly report")


@router.get("/trends/comparison")
async def get_trend_comparison(
    metric: str = Query(..., regex="^(orders|revenue|users|reviews)$"),
    periods: List[str] = Query(["7d", "30d"], description="Periods to compare"),
    current_admin: dict = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Compare trends across different time periods."""
    try:
        comparison_data = {}
        
        for period in periods:
            if metric == "orders":
                analytics = await analytics_service.get_order_analytics(db, period)
                comparison_data[period] = {
                    "total": analytics.total_orders,
                    "trends": analytics.order_trends
                }
            elif metric == "revenue":
                analytics = await analytics_service.get_revenue_analytics(db, period)
                comparison_data[period] = {
                    "total": analytics.total_revenue,
                    "trends": analytics.revenue_by_period
                }
            elif metric == "users":
                analytics = await analytics_service.get_user_analytics(db, period)
                comparison_data[period] = {
                    "total": analytics.total_hospitals + analytics.total_vendors,
                    "trends": analytics.user_growth_trend
                }
            elif metric == "reviews":
                analytics = await analytics_service.get_review_analytics(db, period)
                comparison_data[period] = {
                    "total": analytics.total_reviews,
                    "trends": analytics.review_trends
                }
        
        return {
            "metric": metric,
            "comparison": comparison_data,
            "generated_at": datetime.now(datetime.timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate trend comparison")


def _generate_business_recommendations(
    order_analytics, revenue_analytics, user_analytics, review_analytics
) -> List[str]:
    """Generate business recommendations based on analytics."""
    recommendations = []
    
    # Order completion rate recommendations
    if order_analytics.completion_rate < 85:
        recommendations.append("Consider improving order fulfillment processes to increase completion rate")
    
    # Customer satisfaction recommendations
    if review_analytics.average_rating < 4.0:
        recommendations.append("Focus on improving service quality to increase customer satisfaction")
    
    # Revenue growth recommendations
    if revenue_analytics.platform_fees < revenue_analytics.total_revenue * 0.05:
        recommendations.append("Consider optimizing platform fee structure for better revenue")
    
    # User growth recommendations
    if user_analytics.new_registrations < 50:
        recommendations.append("Implement user acquisition strategies to increase new registrations")
    
    return recommendations
