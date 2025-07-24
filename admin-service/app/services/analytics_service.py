from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, text
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import httpx
import asyncio
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from app.schemas.admin import (
    DashboardKPI, DashboardMetric, OrderAnalytics, RevenueAnalytics,
    UserAnalytics, ReviewAnalytics, SystemAnalytics, ChartDataPoint
)

settings = get_settings()


class AnalyticsService:
    def __init__(self):
        self.settings = settings

    async def get_dashboard_kpis(self, db: AsyncSession, period: str = "30d") -> DashboardKPI:
        """Get key performance indicators for the dashboard."""
        
        # Calculate date range
        end_date = datetime.utcnow()
        if period == "24h":
            start_date = end_date - timedelta(hours=24)
            previous_start = start_date - timedelta(hours=24)
        elif period == "7d":
            start_date = end_date - timedelta(days=7)
            previous_start = start_date - timedelta(days=7)
        elif period == "30d":
            start_date = end_date - timedelta(days=30)
            previous_start = start_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(days=30)
            previous_start = start_date - timedelta(days=30)

        # Fetch data from all services concurrently
        tasks = [
            self._get_order_metrics(start_date, end_date, previous_start),
            self._get_revenue_metrics(start_date, end_date, previous_start),
            self._get_user_metrics(start_date, end_date, previous_start),
            self._get_review_metrics(start_date, end_date, previous_start),
        ]
        
        order_metrics, revenue_metrics, user_metrics, review_metrics = await asyncio.gather(*tasks)
        
        return DashboardKPI(
            total_orders=DashboardMetric(
                title="Total Orders",
                value=order_metrics.get("total", 0),
                change=order_metrics.get("change", 0),
                change_period=period,
                trend=self._determine_trend(order_metrics.get("change", 0))
            ),
            total_revenue=DashboardMetric(
                title="Total Revenue",
                value=revenue_metrics.get("total", 0),
                unit="NGN",
                change=revenue_metrics.get("change", 0),
                change_period=period,
                trend=self._determine_trend(revenue_metrics.get("change", 0))
            ),
            active_users=DashboardMetric(
                title="Active Users",
                value=user_metrics.get("active", 0),
                change=user_metrics.get("change", 0),
                change_period=period,
                trend=self._determine_trend(user_metrics.get("change", 0))
            ),
            average_rating=DashboardMetric(
                title="Average Rating",
                value=review_metrics.get("average_rating", 0),
                unit="stars",
                change=review_metrics.get("rating_change", 0),
                change_period=period,
                trend=self._determine_trend(review_metrics.get("rating_change", 0))
            ),
            platform_fee_revenue=DashboardMetric(
                title="Platform Fees",
                value=revenue_metrics.get("platform_fees", 0),
                unit="NGN",
                change=revenue_metrics.get("fee_change", 0),
                change_period=period,
                trend=self._determine_trend(revenue_metrics.get("fee_change", 0))
            ),
            order_completion_rate=DashboardMetric(
                title="Completion Rate",
                value=order_metrics.get("completion_rate", 0),
                unit="%",
                change=order_metrics.get("completion_change", 0),
                change_period=period,
                trend=self._determine_trend(order_metrics.get("completion_change", 0))
            )
        )

    async def get_order_analytics(self, db: AsyncSession, period: str = "30d") -> OrderAnalytics:
        """Get detailed order analytics."""
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30 if period == "30d" else 7)
        
        try:
            async with httpx.AsyncClient() as client:
                # Get order data from order service
                response = await client.get(
                    f"{self.settings.ORDER_SERVICE_URL}/analytics/orders",
                    params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return OrderAnalytics(
                        total_orders=data.get("total_orders", 0),
                        completed_orders=data.get("completed_orders", 0),
                        cancelled_orders=data.get("cancelled_orders", 0),
                        emergency_orders=data.get("emergency_orders", 0),
                        completion_rate=data.get("completion_rate", 0),
                        average_order_value=data.get("average_order_value", 0),
                        order_trends=self._format_chart_data(data.get("trends", []))
                    )
                else:
                    return self._get_default_order_analytics()
                    
        except Exception as e:
            print(f"Error fetching order analytics: {e}")
            return self._get_default_order_analytics()

    async def get_revenue_analytics(self, db: AsyncSession, period: str = "30d") -> RevenueAnalytics:
        """Get detailed revenue analytics."""
        
        try:
            async with httpx.AsyncClient() as client:
                # Get payment data from payment service
                response = await client.get(
                    f"{self.settings.PAYMENT_SERVICE_URL}/analytics/revenue",
                    params={"period": period}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return RevenueAnalytics(
                        total_revenue=data.get("total_revenue", 0),
                        platform_fees=data.get("platform_fees", 0),
                        vendor_payouts=data.get("vendor_payouts", 0),
                        revenue_by_period=self._format_chart_data(data.get("revenue_trends", [])),
                        top_revenue_vendors=data.get("top_vendors", [])
                    )
                else:
                    return self._get_default_revenue_analytics()
                    
        except Exception as e:
            print(f"Error fetching revenue analytics: {e}")
            return self._get_default_revenue_analytics()

    async def get_user_analytics(self, db: AsyncSession, period: str = "30d") -> UserAnalytics:
        """Get detailed user analytics."""
        
        try:
            async with httpx.AsyncClient() as client:
                # Get user data from user service
                response = await client.get(
                    f"{self.settings.USER_SERVICE_URL}/analytics/users",
                    params={"period": period}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return UserAnalytics(
                        total_hospitals=data.get("total_hospitals", 0),
                        total_vendors=data.get("total_vendors", 0),
                        active_users_24h=data.get("active_users_24h", 0),
                        new_registrations=data.get("new_registrations", 0),
                        user_growth_trend=self._format_chart_data(data.get("growth_trends", [])),
                        geographic_distribution=data.get("geographic_distribution", [])
                    )
                else:
                    return self._get_default_user_analytics()
                    
        except Exception as e:
            print(f"Error fetching user analytics: {e}")
            return self._get_default_user_analytics()

    async def get_review_analytics(self, db: AsyncSession, period: str = "30d") -> ReviewAnalytics:
        """Get detailed review analytics."""
        
        try:
            async with httpx.AsyncClient() as client:
                # Get review data from review service
                response = await client.get(
                    f"{self.settings.REVIEW_SERVICE_URL}/analytics/reviews",
                    params={"period": period}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    return ReviewAnalytics(
                        total_reviews=data.get("total_reviews", 0),
                        average_rating=data.get("average_rating", 0),
                        rating_distribution=data.get("rating_distribution", {}),
                        flagged_reviews=data.get("flagged_reviews", 0),
                        review_trends=self._format_chart_data(data.get("review_trends", []))
                    )
                else:
                    return self._get_default_review_analytics()
                    
        except Exception as e:
            print(f"Error fetching review analytics: {e}")
            return self._get_default_review_analytics()

    async def get_system_analytics(self, db: AsyncSession) -> SystemAnalytics:
        """Get system health and performance analytics."""
        
        service_health = {}
        response_times = {}
        error_rates = {}
        
        services = [
            ("user", self.settings.USER_SERVICE_URL),
            ("order", self.settings.ORDER_SERVICE_URL),
            ("payment", self.settings.PAYMENT_SERVICE_URL),
            ("review", self.settings.REVIEW_SERVICE_URL),
            ("inventory", self.settings.INVENTORY_SERVICE_URL),
            ("pricing", self.settings.PRICING_SERVICE_URL),
            ("notification", self.settings.NOTIFICATION_SERVICE_URL),
        ]
        
        async with httpx.AsyncClient() as client:
            for service_name, service_url in services:
                try:
                    start_time = datetime.utcnow()
                    response = await client.get(f"{service_url}/health", timeout=5.0)
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    service_health[service_name] = "healthy" if response.status_code == 200 else "unhealthy"
                    response_times[service_name] = response_time
                    error_rates[service_name] = 0.0  # Would be calculated from metrics
                    
                except Exception:
                    service_health[service_name] = "down"
                    response_times[service_name] = 0.0
                    error_rates[service_name] = 100.0
        
        # Calculate overall uptime
        healthy_services = sum(1 for status in service_health.values() if status == "healthy")
        uptime_percentage = (healthy_services / len(services)) * 100 if services else 0
        
        return SystemAnalytics(
            service_health=service_health,
            response_times=response_times,
            error_rates=error_rates,
            uptime_percentage=uptime_percentage
        )

    # Helper methods
    async def _get_order_metrics(self, start_date: datetime, end_date: datetime, previous_start: datetime) -> Dict[str, Any]:
        """Get order metrics from order service."""
        try:
            async with httpx.AsyncClient() as client:
                current_response = await client.get(
                    f"{self.settings.ORDER_SERVICE_URL}/analytics/summary",
                    params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                )
                previous_response = await client.get(
                    f"{self.settings.ORDER_SERVICE_URL}/analytics/summary",
                    params={"start_date": previous_start.isoformat(), "end_date": start_date.isoformat()}
                )

                current_data = current_response.json() if current_response.status_code == 200 else {}
                previous_data = previous_response.json() if previous_response.status_code == 200 else {}

                current_total = current_data.get("total_orders", 0)
                previous_total = previous_data.get("total_orders", 0)
                change = self._calculate_percentage_change(current_total, previous_total)

                current_completed = current_data.get("completed_orders", 0)
                completion_rate = (current_completed / current_total * 100) if current_total > 0 else 0

                previous_completed = previous_data.get("completed_orders", 0)
                previous_completion_rate = (previous_completed / previous_total * 100) if previous_total > 0 else 0
                completion_change = completion_rate - previous_completion_rate

                return {
                    "total": current_total,
                    "change": change,
                    "completion_rate": completion_rate,
                    "completion_change": completion_change
                }
        except Exception as e:
            print(f"Error fetching order metrics: {e}")
            return {"total": 0, "change": 0, "completion_rate": 0, "completion_change": 0}

    async def _get_revenue_metrics(self, start_date: datetime, end_date: datetime, previous_start: datetime) -> Dict[str, Any]:
        """Get revenue metrics from payment service."""
        try:
            async with httpx.AsyncClient() as client:
                current_response = await client.get(
                    f"{self.settings.PAYMENT_SERVICE_URL}/analytics/summary",
                    params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                )
                previous_response = await client.get(
                    f"{self.settings.PAYMENT_SERVICE_URL}/analytics/summary",
                    params={"start_date": previous_start.isoformat(), "end_date": start_date.isoformat()}
                )

                current_data = current_response.json() if current_response.status_code == 200 else {}
                previous_data = previous_response.json() if previous_response.status_code == 200 else {}

                current_revenue = current_data.get("total_revenue", 0)
                previous_revenue = previous_data.get("total_revenue", 0)
                revenue_change = self._calculate_percentage_change(current_revenue, previous_revenue)

                current_fees = current_data.get("platform_fees", 0)
                previous_fees = previous_data.get("platform_fees", 0)
                fee_change = self._calculate_percentage_change(current_fees, previous_fees)

                return {
                    "total": current_revenue,
                    "change": revenue_change,
                    "platform_fees": current_fees,
                    "fee_change": fee_change
                }
        except Exception as e:
            print(f"Error fetching revenue metrics: {e}")
            return {"total": 0, "change": 0, "platform_fees": 0, "fee_change": 0}

    async def _get_user_metrics(self, start_date: datetime, end_date: datetime, previous_start: datetime) -> Dict[str, Any]:
        """Get user metrics from user service."""
        try:
            async with httpx.AsyncClient() as client:
                current_response = await client.get(
                    f"{self.settings.USER_SERVICE_URL}/analytics/summary",
                    params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                )
                previous_response = await client.get(
                    f"{self.settings.USER_SERVICE_URL}/analytics/summary",
                    params={"start_date": previous_start.isoformat(), "end_date": start_date.isoformat()}
                )

                current_data = current_response.json() if current_response.status_code == 200 else {}
                previous_data = previous_response.json() if previous_response.status_code == 200 else {}

                current_active = current_data.get("active_users", 0)
                previous_active = previous_data.get("active_users", 0)
                change = self._calculate_percentage_change(current_active, previous_active)

                return {
                    "active": current_active,
                    "change": change
                }
        except Exception as e:
            print(f"Error fetching user metrics: {e}")
            return {"active": 0, "change": 0}

    async def _get_review_metrics(self, start_date: datetime, end_date: datetime, previous_start: datetime) -> Dict[str, Any]:
        """Get review metrics from review service."""
        try:
            async with httpx.AsyncClient() as client:
                current_response = await client.get(
                    f"{self.settings.REVIEW_SERVICE_URL}/analytics/summary",
                    params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
                )
                previous_response = await client.get(
                    f"{self.settings.REVIEW_SERVICE_URL}/analytics/summary",
                    params={"start_date": previous_start.isoformat(), "end_date": start_date.isoformat()}
                )

                current_data = current_response.json() if current_response.status_code == 200 else {}
                previous_data = previous_response.json() if previous_response.status_code == 200 else {}

                current_rating = current_data.get("average_rating", 0)
                previous_rating = previous_data.get("average_rating", 0)
                rating_change = current_rating - previous_rating

                return {
                    "average_rating": current_rating,
                    "rating_change": rating_change
                }
        except Exception as e:
            print(f"Error fetching review metrics: {e}")
            return {"average_rating": 0, "rating_change": 0}

    def _calculate_percentage_change(self, current: float, previous: float) -> float:
        """Calculate percentage change between two values."""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return ((current - previous) / previous) * 100

    def _determine_trend(self, change: float) -> str:
        """Determine trend direction based on change percentage."""
        if change > 5:
            return "up"
        elif change < -5:
            return "down"
        else:
            return "stable"

    def _format_chart_data(self, data: List[Dict[str, Any]]) -> List[ChartDataPoint]:
        """Format data for chart display."""
        return [
            ChartDataPoint(
                x=item.get("date", item.get("x", "")),
                y=item.get("value", item.get("y", 0)),
                label=item.get("label")
            )
            for item in data
        ]

    def _get_default_order_analytics(self) -> OrderAnalytics:
        """Return default order analytics when service is unavailable."""
        return OrderAnalytics(
            total_orders=0,
            completed_orders=0,
            cancelled_orders=0,
            emergency_orders=0,
            completion_rate=0,
            average_order_value=0,
            order_trends=[]
        )

    def _get_default_revenue_analytics(self) -> RevenueAnalytics:
        """Return default revenue analytics when service is unavailable."""
        return RevenueAnalytics(
            total_revenue=0,
            platform_fees=0,
            vendor_payouts=0,
            revenue_by_period=[],
            top_revenue_vendors=[]
        )

    def _get_default_user_analytics(self) -> UserAnalytics:
        """Return default user analytics when service is unavailable."""
        return UserAnalytics(
            total_hospitals=0,
            total_vendors=0,
            active_users_24h=0,
            new_registrations=0,
            user_growth_trend=[],
            geographic_distribution=[]
        )

    def _get_default_review_analytics(self) -> ReviewAnalytics:
        """Return default review analytics when service is unavailable."""
        return ReviewAnalytics(
            total_reviews=0,
            average_rating=0,
            rating_distribution={},
            flagged_reviews=0,
            review_trends=[]
        )
