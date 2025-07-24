import pytest
from unittest.mock import AsyncMock, patch
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.schemas.admin import DashboardKPI, DashboardMetric, OrderAnalytics, RevenueAnalytics


class TestDashboardAPI:
    
    @pytest.mark.asyncio
    async def test_get_dashboard_kpis_success(self, client, admin_headers):
        """Test successful dashboard KPIs retrieval."""
        
        mock_kpis = DashboardKPI(
            total_orders=DashboardMetric(title="Total Orders", value=150, change=15.5, trend="up"),
            total_revenue=DashboardMetric(title="Total Revenue", value=750000, unit="NGN", change=12.3, trend="up"),
            active_users=DashboardMetric(title="Active Users", value=70, change=5.2, trend="up"),
            average_rating=DashboardMetric(title="Average Rating", value=4.2, unit="stars", change=0.1, trend="stable"),
            platform_fee_revenue=DashboardMetric(title="Platform Fees", value=37500, unit="NGN", change=8.7, trend="up"),
            order_completion_rate=DashboardMetric(title="Completion Rate", value=90.0, unit="%", change=2.5, trend="up")
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_dashboard_kpis', return_value=mock_kpis):
            response = await client.get("/admin/dashboard/kpis", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_orders"]["value"] == 150
            assert data["total_revenue"]["value"] == 750000
            assert data["active_users"]["value"] == 70
    
    @pytest.mark.asyncio
    async def test_get_dashboard_kpis_non_admin(self, client, non_admin_headers):
        """Test dashboard KPIs access denied for non-admin users."""
        
        response = await client.get("/admin/dashboard/kpis", headers=non_admin_headers)
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_order_analytics_success(self, client, admin_headers):
        """Test successful order analytics retrieval."""
        
        mock_analytics = OrderAnalytics(
            total_orders=100,
            completed_orders=85,
            cancelled_orders=10,
            emergency_orders=15,
            completion_rate=85.0,
            average_order_value=5000.0,
            order_trends=[]
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_order_analytics', return_value=mock_analytics):
            response = await client.get("/admin/dashboard/analytics/orders", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_orders"] == 100
            assert data["completed_orders"] == 85
            assert data["completion_rate"] == 85.0
    
    @pytest.mark.asyncio
    async def test_get_revenue_analytics_success(self, client, admin_headers):
        """Test successful revenue analytics retrieval."""
        
        mock_analytics = RevenueAnalytics(
            total_revenue=500000,
            platform_fees=25000,
            vendor_payouts=475000,
            revenue_by_period=[],
            top_revenue_vendors=[]
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_revenue_analytics', return_value=mock_analytics):
            response = await client.get("/admin/dashboard/analytics/revenue", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_revenue"] == 500000
            assert data["platform_fees"] == 25000
            assert data["vendor_payouts"] == 475000
    
    @pytest.mark.asyncio
    async def test_get_system_health_success(self, client, admin_headers):
        """Test successful system health retrieval."""
        
        from app.schemas.admin import SystemHealthResponse, ServiceHealthStatus
        
        mock_health = SystemHealthResponse(
            overall_status="healthy",
            services=[
                ServiceHealthStatus(
                    service_name="user-service",
                    status="healthy",
                    response_time=150.0,
                    last_check=pytest.datetime.utcnow()
                )
            ],
            database_status="healthy",
            redis_status="healthy",
            rabbitmq_status="healthy"
        )
        
        with patch('app.services.system_monitoring_service.SystemMonitoringService.get_system_health', return_value=mock_health):
            response = await client.get("/admin/dashboard/health", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["overall_status"] == "healthy"
            assert data["database_status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_get_system_overview_success(self, client, admin_headers):
        """Test successful system overview retrieval."""
        
        mock_overview = {
            "system_resources": {
                "cpu_usage": 45.2,
                "memory_usage": 68.5,
                "disk_usage": 32.1
            },
            "service_health": {
                "user-service": "healthy",
                "order-service": "healthy"
            },
            "alerts": {
                "active_count": 2,
                "last_24h": 5
            }
        }
        
        with patch('app.services.system_monitoring_service.SystemMonitoringService.get_system_overview', return_value=mock_overview):
            response = await client.get("/admin/dashboard/overview", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["system_resources"]["cpu_usage"] == 45.2
            assert data["alerts"]["active_count"] == 2
    
    @pytest.mark.asyncio
    async def test_get_service_metrics_success(self, client, admin_headers):
        """Test successful service metrics retrieval."""
        
        mock_metrics = [
            {
                "timestamp": "2024-01-01T10:00:00Z",
                "value": 150.5,
                "unit": "milliseconds",
                "metadata": {"service": "user-service"}
            }
        ]
        
        with patch('app.services.system_monitoring_service.SystemMonitoringService.get_service_metrics', return_value=mock_metrics):
            response = await client.get(
                "/admin/dashboard/metrics/user-service?metric_type=response_time&hours=24",
                headers=admin_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "user-service"
            assert data["metric_type"] == "response_time"
            assert len(data["data"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_service_metrics_invalid_type(self, client, admin_headers):
        """Test service metrics with invalid metric type."""
        
        response = await client.get(
            "/admin/dashboard/metrics/user-service?metric_type=invalid_type",
            headers=admin_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_trigger_metrics_collection_success(self, client, admin_headers):
        """Test successful metrics collection trigger."""
        
        with patch('app.services.system_monitoring_service.SystemMonitoringService.collect_system_metrics'):
            response = await client.post("/admin/dashboard/metrics/collect", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "triggered successfully" in data["message"]
    
    @pytest.mark.asyncio
    async def test_get_order_trends_chart_success(self, client, admin_headers):
        """Test successful order trends chart data retrieval."""
        
        mock_analytics = OrderAnalytics(
            total_orders=100,
            completed_orders=85,
            cancelled_orders=10,
            emergency_orders=15,
            completion_rate=85.0,
            average_order_value=5000.0,
            order_trends=[
                type('ChartDataPoint', (), {"x": "2024-01-01", "y": 10})(),
                type('ChartDataPoint', (), {"x": "2024-01-02", "y": 15})()
            ]
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_order_analytics', return_value=mock_analytics):
            response = await client.get("/admin/dashboard/charts/order-trends", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Order Trends"
            assert data["type"] == "line"
            assert "data" in data
    
    @pytest.mark.asyncio
    async def test_get_revenue_breakdown_chart_success(self, client, admin_headers):
        """Test successful revenue breakdown chart data retrieval."""
        
        mock_analytics = RevenueAnalytics(
            total_revenue=500000,
            platform_fees=25000,
            vendor_payouts=475000,
            revenue_by_period=[],
            top_revenue_vendors=[]
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_revenue_analytics', return_value=mock_analytics):
            response = await client.get("/admin/dashboard/charts/revenue-breakdown", headers=admin_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Revenue Breakdown"
            assert data["type"] == "doughnut"
            assert "data" in data
    
    @pytest.mark.asyncio
    async def test_dashboard_kpis_with_different_periods(self, client, admin_headers):
        """Test dashboard KPIs with different time periods."""
        
        mock_kpis = DashboardKPI(
            total_orders=DashboardMetric(title="Total Orders", value=50, change=5.0, trend="up"),
            total_revenue=DashboardMetric(title="Total Revenue", value=250000, unit="NGN", change=3.2, trend="up"),
            active_users=DashboardMetric(title="Active Users", value=30, change=2.1, trend="up"),
            average_rating=DashboardMetric(title="Average Rating", value=4.1, unit="stars", change=-0.1, trend="down"),
            platform_fee_revenue=DashboardMetric(title="Platform Fees", value=12500, unit="NGN", change=3.2, trend="up"),
            order_completion_rate=DashboardMetric(title="Completion Rate", value=88.0, unit="%", change=-1.0, trend="down")
        )
        
        with patch('app.services.analytics_service.AnalyticsService.get_dashboard_kpis', return_value=mock_kpis):
            # Test 24h period
            response = await client.get("/admin/dashboard/kpis?period=24h", headers=admin_headers)
            assert response.status_code == 200
            
            # Test 7d period
            response = await client.get("/admin/dashboard/kpis?period=7d", headers=admin_headers)
            assert response.status_code == 200
            
            # Test invalid period
            response = await client.get("/admin/dashboard/kpis?period=invalid", headers=admin_headers)
            assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_analytics_service_error_handling(self, client, admin_headers):
        """Test error handling when analytics service fails."""
        
        with patch('app.services.analytics_service.AnalyticsService.get_dashboard_kpis', side_effect=Exception("Service error")):
            response = await client.get("/admin/dashboard/kpis", headers=admin_headers)
            
            assert response.status_code == 500
            assert "Failed to fetch dashboard KPIs" in response.json()["detail"]
