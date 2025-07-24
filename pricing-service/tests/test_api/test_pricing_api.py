import pytest
from unittest.mock import AsyncMock, patch
import json
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class TestPricingAPI:
    
    @pytest.mark.asyncio
    async def test_create_quote_request_success(self, client, hospital_headers, sample_quote_request_data, mock_httpx_client):
        """Test successful quote request creation."""
        
        response = await client.post(
            "/quote-requests",
            json=sample_quote_request_data,
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "quote_request_id" in data["data"]
    
    @pytest.mark.asyncio
    async def test_create_quote_request_non_hospital(self, client, vendor_headers, sample_quote_request_data):
        """Test quote request creation by non-hospital user."""
        
        response = await client.post(
            "/quote-requests",
            json=sample_quote_request_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 403
        assert "Only hospitals can create quote requests" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_quote_requests_success(self, client, hospital_headers, sample_quote_request):
        """Test successful quote requests retrieval."""
        
        response = await client.get(
            "/quote-requests",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
    
    @pytest.mark.asyncio
    async def test_get_quote_requests_with_filters(self, client, hospital_headers):
        """Test quote requests retrieval with filters."""
        
        response = await client.get(
            "/quote-requests?status=open&cylinder_size=MEDIUM",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    @pytest.mark.asyncio
    async def test_get_quote_request_success(self, client, hospital_headers, sample_quote_request):
        """Test getting specific quote request."""
        
        response = await client.get(
            f"/quote-requests/{sample_quote_request.id}",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_quote_request.id
        assert data["hospital_id"] == sample_quote_request.hospital_id
    
    @pytest.mark.asyncio
    async def test_get_quote_request_not_found(self, client, hospital_headers):
        """Test getting non-existent quote request."""
        
        import uuid
        
        response = await client.get(
            f"/quote-requests/{uuid.uuid4()}",
            headers=hospital_headers
        )
        
        assert response.status_code == 404
        assert "Quote request not found" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_submit_bid_success(self, client, vendor_headers, sample_quote_request, sample_bid_data, mock_httpx_client):
        """Test successful bid submission."""
        
        response = await client.post(
            f"/quote-requests/{sample_quote_request.id}/bids",
            json=sample_bid_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "bid_id" in data["data"]
    
    @pytest.mark.asyncio
    async def test_submit_bid_non_vendor(self, client, hospital_headers, sample_quote_request, sample_bid_data):
        """Test bid submission by non-vendor user."""
        
        response = await client.post(
            f"/quote-requests/{sample_quote_request.id}/bids",
            json=sample_bid_data,
            headers=hospital_headers
        )
        
        assert response.status_code == 403
        assert "Only vendors can submit bids" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_bids_for_quote_request(self, client, hospital_headers, sample_quote_request, sample_bid):
        """Test getting bids for a quote request."""
        
        response = await client.get(
            f"/quote-requests/{sample_quote_request.id}/bids",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(bid["id"] == sample_bid.id for bid in data)
    
    @pytest.mark.asyncio
    async def test_get_ranked_bids_success(self, client, hospital_headers, sample_quote_request, sample_bid):
        """Test getting ranked bids for a quote request."""
        
        response = await client.get(
            f"/quote-requests/{sample_quote_request.id}/bids/ranked",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "quote_request_id" in data
        assert "ranked_bids" in data
        assert data["quote_request_id"] == sample_quote_request.id
    
    @pytest.mark.asyncio
    async def test_get_ranked_bids_non_hospital(self, client, vendor_headers, sample_quote_request):
        """Test getting ranked bids by non-hospital user."""
        
        response = await client.get(
            f"/quote-requests/{sample_quote_request.id}/bids/ranked",
            headers=vendor_headers
        )
        
        assert response.status_code == 403
        assert "Only hospitals can view ranked bids" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_accept_bid_success(self, client, hospital_headers, sample_bid, mock_httpx_client):
        """Test successful bid acceptance."""
        
        response = await client.post(
            f"/bids/{sample_bid.id}/accept",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["bid_id"] == sample_bid.id
        assert data["data"]["vendor_id"] == sample_bid.vendor_id
    
    @pytest.mark.asyncio
    async def test_accept_bid_non_hospital(self, client, vendor_headers, sample_bid):
        """Test bid acceptance by non-hospital user."""
        
        response = await client.post(
            f"/bids/{sample_bid.id}/accept",
            headers=vendor_headers
        )
        
        assert response.status_code == 403
        assert "Only hospitals can accept bids" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_vendor_bids(self, client, vendor_headers):
        """Test getting vendor's bids."""
        
        response = await client.get(
            "/vendor/bids",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
    
    @pytest.mark.asyncio
    async def test_get_vendor_bids_non_vendor(self, client, hospital_headers):
        """Test getting vendor bids by non-vendor user."""
        
        response = await client.get(
            "/vendor/bids",
            headers=hospital_headers
        )
        
        assert response.status_code == 403
        assert "Only vendors can access this endpoint" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_pricing_overview_admin(self, client, admin_headers, sample_price_history):
        """Test getting pricing overview as admin."""
        
        response = await client.get(
            "/analytics/overview",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_quote_requests" in data
        assert "total_bids" in data
        assert "bid_success_rate" in data
    
    @pytest.mark.asyncio
    async def test_get_pricing_overview_hospital(self, client, hospital_headers):
        """Test getting pricing overview as hospital."""
        
        response = await client.get(
            "/analytics/overview",
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_quote_requests" in data
    
    @pytest.mark.asyncio
    async def test_get_pricing_overview_vendor_forbidden(self, client, vendor_headers):
        """Test that vendors cannot access pricing overview."""
        
        response = await client.get(
            "/analytics/overview",
            headers=vendor_headers
        )
        
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_price_trends(self, client, admin_headers, sample_price_history):
        """Test getting price trends."""
        
        response = await client.get(
            "/analytics/price-trends?cylinder_size=MEDIUM&days=30",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "cylinder_size" in data
        assert "period_days" in data
        assert "trends" in data
    
    @pytest.mark.asyncio
    async def test_get_vendor_performance_own_data(self, client, vendor_headers, sample_vendor_performance):
        """Test vendor getting their own performance data."""
        
        response = await client.get(
            "/analytics/vendor-performance",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "vendor_count" in data
        assert "vendors" in data
    
    @pytest.mark.asyncio
    async def test_get_vendor_performance_admin(self, client, admin_headers, sample_vendor_performance):
        """Test admin getting vendor performance data."""
        
        response = await client.get(
            f"/analytics/vendor-performance?vendor_id={sample_vendor_performance.vendor_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "vendor_count" in data
        assert "vendors" in data
    
    @pytest.mark.asyncio
    async def test_get_market_insights(self, client, admin_headers):
        """Test getting market insights."""
        
        response = await client.get(
            "/analytics/market-insights?days=30",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert "average_bids_per_request" in data
        assert "price_distribution" in data
    
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health check endpoint."""
        
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "pricing-service"
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_invalid_quote_request_data(self, client, hospital_headers):
        """Test quote request creation with invalid data."""
        
        invalid_data = {
            "cylinder_size": "INVALID_SIZE",
            "quantity": -5,  # Invalid negative quantity
            "delivery_address": "",  # Empty address
            "delivery_latitude": 200,  # Invalid latitude
            "delivery_longitude": 200,  # Invalid longitude
            "required_delivery_date": "invalid-date"
        }
        
        response = await client.post(
            "/quote-requests",
            json=invalid_data,
            headers=hospital_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_invalid_bid_data(self, client, vendor_headers, sample_quote_request):
        """Test bid submission with invalid data."""
        
        invalid_bid_data = {
            "unit_price": -100,  # Invalid negative price
            "delivery_fee": -50,  # Invalid negative fee
            "estimated_delivery_time_hours": 0  # Invalid zero delivery time
        }
        
        response = await client.post(
            f"/quote-requests/{sample_quote_request.id}/bids",
            json=invalid_bid_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 422  # Validation error
