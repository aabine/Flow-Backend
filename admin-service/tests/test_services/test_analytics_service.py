import pytest
from unittest.mock import AsyncMock, patch
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.analytics_service import AnalyticsService
from app.schemas.admin import DashboardKPI, OrderAnalytics, RevenueAnalytics


class TestAnalyticsService:
    
    @pytest.fixture
    def analytics_service(self):
        return AnalyticsService()
    
    @pytest.mark.asyncio
    async def test_get_dashboard_kpis_success(self, analytics_service, db_session, sample_analytics_data):
        """Test successful dashboard KPIs retrieval."""
        
        with patch.object(analytics_service, '_get_order_metrics', return_value={
            "total": 150, "change": 15.5, "completion_rate": 90.0, "completion_change": 2.5
        }), \
        patch.object(analytics_service, '_get_revenue_metrics', return_value={
            "total": 750000, "change": 12.3, "platform_fees": 37500, "fee_change": 8.7
        }), \
        patch.object(analytics_service, '_get_user_metrics', return_value={
            "active": 70, "change": 5.2
        }), \
        patch.object(analytics_service, '_get_review_metrics', return_value={
            "average_rating": 4.2, "rating_change": 0.1
        }):
            
            kpis = await analytics_service.get_dashboard_kpis(db_session, "30d")
            
            assert isinstance(kpis, DashboardKPI)
            assert kpis.total_orders.value == 150
            assert kpis.total_revenue.value == 750000
            assert kpis.active_users.value == 70
            assert kpis.average_rating.value == 4.2
            assert kpis.platform_fee_revenue.value == 37500
            assert kpis.order_completion_rate.value == 90.0
    
    @pytest.mark.asyncio
    async def test_get_order_analytics_success(self, analytics_service, db_session):
        """Test successful order analytics retrieval."""
        
        mock_response_data = {
            "total_orders": 100,
            "completed_orders": 85,
            "cancelled_orders": 10,
            "emergency_orders": 15,
            "completion_rate": 85.0,
            "average_order_value": 5000.0,
            "trends": [{"date": "2024-01-01", "value": 10}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            analytics = await analytics_service.get_order_analytics(db_session, "30d")
            
            assert isinstance(analytics, OrderAnalytics)
            assert analytics.total_orders == 100
            assert analytics.completed_orders == 85
            assert analytics.completion_rate == 85.0
    
    @pytest.mark.asyncio
    async def test_get_revenue_analytics_success(self, analytics_service, db_session):
        """Test successful revenue analytics retrieval."""
        
        mock_response_data = {
            "total_revenue": 500000,
            "platform_fees": 25000,
            "vendor_payouts": 475000,
            "revenue_trends": [{"date": "2024-01-01", "value": 50000}],
            "top_vendors": [{"vendor_id": "vendor-1", "revenue": 100000}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            analytics = await analytics_service.get_revenue_analytics(db_session, "30d")
            
            assert isinstance(analytics, RevenueAnalytics)
            assert analytics.total_revenue == 500000
            assert analytics.platform_fees == 25000
            assert analytics.vendor_payouts == 475000
    
    @pytest.mark.asyncio
    async def test_get_order_analytics_service_unavailable(self, analytics_service, db_session):
        """Test order analytics when service is unavailable."""
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            analytics = await analytics_service.get_order_analytics(db_session, "30d")
            
            # Should return default analytics
            assert analytics.total_orders == 0
            assert analytics.completed_orders == 0
            assert analytics.order_trends == []
    
    @pytest.mark.asyncio
    async def test_get_system_analytics_success(self, analytics_service, db_session):
        """Test successful system analytics retrieval."""
        
        with patch('httpx.AsyncClient') as mock_client:
            # Mock health check responses
            mock_response = AsyncMock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            analytics = await analytics_service.get_system_analytics(db_session)
            
            assert "user" in analytics.service_health
            assert "order" in analytics.service_health
            assert "payment" in analytics.service_health
            assert analytics.uptime_percentage >= 0
            assert analytics.uptime_percentage <= 100
    
    def test_calculate_percentage_change(self, analytics_service):
        """Test percentage change calculation."""
        
        # Normal case
        change = analytics_service._calculate_percentage_change(120, 100)
        assert change == 20.0
        
        # Decrease case
        change = analytics_service._calculate_percentage_change(80, 100)
        assert change == -20.0
        
        # Zero previous value
        change = analytics_service._calculate_percentage_change(50, 0)
        assert change == 100.0
        
        # Zero current value
        change = analytics_service._calculate_percentage_change(0, 100)
        assert change == -100.0
    
    def test_determine_trend(self, analytics_service):
        """Test trend determination logic."""
        
        assert analytics_service._determine_trend(10.0) == "up"
        assert analytics_service._determine_trend(-10.0) == "down"
        assert analytics_service._determine_trend(2.0) == "stable"
        assert analytics_service._determine_trend(-2.0) == "stable"
    
    def test_format_chart_data(self, analytics_service):
        """Test chart data formatting."""
        
        raw_data = [
            {"date": "2024-01-01", "value": 10},
            {"x": "2024-01-02", "y": 15, "label": "Test"}
        ]
        
        formatted = analytics_service._format_chart_data(raw_data)
        
        assert len(formatted) == 2
        assert formatted[0].x == "2024-01-01"
        assert formatted[0].y == 10
        assert formatted[1].x == "2024-01-02"
        assert formatted[1].y == 15
        assert formatted[1].label == "Test"
    
    @pytest.mark.asyncio
    async def test_get_order_metrics_http_error(self, analytics_service):
        """Test order metrics retrieval with HTTP error."""
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.RequestError("Connection failed")
            
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            previous_start = start_date - timedelta(days=30)
            
            metrics = await analytics_service._get_order_metrics(start_date, end_date, previous_start)
            
            # Should return default values on error
            assert metrics["total"] == 0
            assert metrics["change"] == 0
            assert metrics["completion_rate"] == 0
    
    @pytest.mark.asyncio
    async def test_get_revenue_metrics_success(self, analytics_service):
        """Test successful revenue metrics retrieval."""
        
        mock_current_data = {"total_revenue": 100000, "platform_fees": 5000}
        mock_previous_data = {"total_revenue": 80000, "platform_fees": 4000}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_current_response = AsyncMock()
            mock_current_response.status_code = 200
            mock_current_response.json.return_value = mock_current_data
            
            mock_previous_response = AsyncMock()
            mock_previous_response.status_code = 200
            mock_previous_response.json.return_value = mock_previous_data
            
            mock_client.return_value.__aenter__.return_value.get.side_effect = [
                mock_current_response, mock_previous_response
            ]
            
            from datetime import datetime, timedelta
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            previous_start = start_date - timedelta(days=30)
            
            metrics = await analytics_service._get_revenue_metrics(start_date, end_date, previous_start)
            
            assert metrics["total"] == 100000
            assert metrics["platform_fees"] == 5000
            assert metrics["change"] == 25.0  # (100000 - 80000) / 80000 * 100
            assert metrics["fee_change"] == 25.0  # (5000 - 4000) / 4000 * 100
