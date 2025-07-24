import pytest
from httpx import AsyncClient
from unittest.mock import patch


class TestDeliveryAPI:
    """Test cases for Delivery API endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["service"] == "delivery-service"

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "delivery-service"
        assert "version" in data

    @pytest.mark.asyncio
    @patch("app.api.deliveries.get_current_user")
    async def test_create_delivery(self, mock_auth, client: AsyncClient, 
                                 sample_delivery_data, mock_current_user):
        """Test creating a delivery via API."""
        mock_auth.return_value = mock_current_user
        
        response = await client.post(
            "/api/v1/deliveries/",
            json=sample_delivery_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "delivery_id" in data["data"]

    @pytest.mark.asyncio
    @patch("app.api.deliveries.get_current_user")
    async def test_get_deliveries(self, mock_auth, client: AsyncClient, mock_current_user):
        """Test getting deliveries via API."""
        mock_auth.return_value = mock_current_user
        
        response = await client.get("/api/v1/deliveries/")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data

    @pytest.mark.asyncio
    @patch("app.api.deliveries.get_current_user")
    async def test_calculate_eta(self, mock_auth, client: AsyncClient, mock_current_user):
        """Test ETA calculation via API."""
        mock_auth.return_value = mock_current_user
        
        eta_request = {
            "pickup_lat": 6.5244,
            "pickup_lng": 3.3792,
            "delivery_lat": 6.4474,
            "delivery_lng": 3.3903,
            "priority": "NORMAL"
        }
        
        response = await client.post(
            "/api/v1/deliveries/calculate-eta",
            json=eta_request
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "distance_km" in data
        assert "estimated_duration_minutes" in data
        assert "estimated_pickup_time" in data
        assert "estimated_delivery_time" in data


class TestDriverAPI:
    """Test cases for Driver API endpoints."""

    @pytest.mark.asyncio
    @patch("app.api.drivers.get_current_user")
    async def test_create_driver(self, mock_auth, client: AsyncClient, 
                               sample_driver_data, mock_current_user):
        """Test creating a driver via API."""
        mock_auth.return_value = mock_current_user
        
        response = await client.post(
            "/api/v1/drivers/",
            json=sample_driver_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "driver_id" in data["data"]

    @pytest.mark.asyncio
    @patch("app.api.drivers.get_current_user")
    async def test_get_available_drivers_near(self, mock_auth, client: AsyncClient, mock_current_user):
        """Test getting available drivers near location via API."""
        mock_auth.return_value = mock_current_user
        
        response = await client.get(
            "/api/v1/drivers/available/near",
            params={"lat": 6.5244, "lng": 3.3792}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestRouteAPI:
    """Test cases for Route API endpoints."""

    @pytest.mark.asyncio
    @patch("app.api.routes.get_current_user")
    async def test_create_route_invalid_data(self, mock_auth, client: AsyncClient, mock_current_user):
        """Test creating a route with invalid data via API."""
        mock_auth.return_value = mock_current_user
        
        route_data = {
            "driver_id": "invalid-driver-id",
            "delivery_ids": ["invalid-delivery-id"]
        }
        
        response = await client.post(
            "/api/v1/routes/",
            json=route_data
        )
        
        # Should return error for invalid data
        assert response.status_code in [400, 500]
