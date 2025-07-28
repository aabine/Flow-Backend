import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import json

from app.models.vendor import Vendor


class TestVendorsAPI:
    """Test cases for Vendors API endpoints."""

    @pytest.fixture
    async def sample_vendor(self, db_session, sample_vendor_data):
        """Create a sample vendor in the database."""
        vendor = Vendor(**sample_vendor_data)
        db_session.add(vendor)
        await db_session.commit()
        await db_session.refresh(vendor)
        return vendor

    async def test_get_nearby_vendors_success(self, client: AsyncClient, sample_vendor, mock_hospital_user):
        """Test successful nearby vendors search."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get(
                "/api/v1/vendors/nearby",
                params={
                    "latitude": 6.5244,
                    "longitude": 3.3792,
                    "radius_km": 50.0,
                    "page": 1,
                    "page_size": 10
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "vendors" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["page"] == 1
        assert data["page_size"] == 10

    async def test_get_nearby_vendors_unauthorized_role(self, client: AsyncClient, mock_vendor_user):
        """Test nearby vendors search with unauthorized role."""
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            response = await client.get(
                "/api/v1/vendors/nearby",
                params={
                    "latitude": 6.5244,
                    "longitude": 3.3792,
                    "radius_km": 50.0
                }
            )
        
        assert response.status_code == 403
        assert "Only hospitals can search for vendors" in response.json()["detail"]

    async def test_get_nearby_vendors_invalid_coordinates(self, client: AsyncClient, mock_hospital_user):
        """Test nearby vendors search with invalid coordinates."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get(
                "/api/v1/vendors/nearby",
                params={
                    "latitude": 91.0,  # Invalid latitude
                    "longitude": 3.3792,
                    "radius_km": 50.0
                }
            )
        
        assert response.status_code == 422  # Validation error

    async def test_get_vendor_details_success(self, client: AsyncClient, sample_vendor, mock_hospital_user):
        """Test successful vendor details retrieval."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get(f"/api/v1/vendors/{sample_vendor.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_vendor.id)
        assert data["business_name"] == sample_vendor.business_name
        assert data["verification_status"] == sample_vendor.verification_status

    async def test_get_vendor_details_not_found(self, client: AsyncClient, mock_hospital_user):
        """Test vendor details retrieval for non-existent vendor."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get("/api/v1/vendors/550e8400-e29b-41d4-a716-446655440999")
        
        assert response.status_code == 404
        assert "Vendor not found" in response.json()["detail"]

    async def test_get_vendor_service_areas_success(self, client: AsyncClient, sample_vendor, mock_hospital_user):
        """Test successful vendor service areas retrieval."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get(f"/api/v1/vendors/{sample_vendor.id}/service-areas")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_vendor_success(self, client: AsyncClient, mock_vendor_user, sample_vendor_data):
        """Test successful vendor creation."""
        vendor_data = sample_vendor_data.copy()
        vendor_data["user_id"] = mock_vendor_user["user_id"]
        
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            with patch('app.services.event_service.event_service.publish_vendor_added', new_callable=AsyncMock):
                response = await client.post(
                    "/api/v1/vendors/",
                    json=vendor_data
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["business_name"] == vendor_data["business_name"]
        assert data["user_id"] == vendor_data["user_id"]
        assert data["verification_status"] == "pending"

    async def test_create_vendor_unauthorized_role(self, client: AsyncClient, mock_hospital_user, sample_vendor_data):
        """Test vendor creation with unauthorized role."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.post(
                "/api/v1/vendors/",
                json=sample_vendor_data
            )
        
        assert response.status_code == 403
        assert "Only vendors can create vendor profiles" in response.json()["detail"]

    async def test_create_vendor_wrong_user_id(self, client: AsyncClient, mock_vendor_user, sample_vendor_data):
        """Test vendor creation with wrong user ID."""
        vendor_data = sample_vendor_data.copy()
        vendor_data["user_id"] = "550e8400-e29b-41d4-a716-446655440999"  # Different user ID
        
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            response = await client.post(
                "/api/v1/vendors/",
                json=vendor_data
            )
        
        assert response.status_code == 403
        assert "You can only create your own vendor profile" in response.json()["detail"]

    async def test_create_vendor_duplicate(self, client: AsyncClient, sample_vendor, mock_vendor_user, sample_vendor_data):
        """Test creating duplicate vendor profile."""
        vendor_data = sample_vendor_data.copy()
        vendor_data["user_id"] = mock_vendor_user["user_id"]
        
        # First, update the existing vendor to have the same user_id
        sample_vendor.user_id = mock_vendor_user["user_id"]
        
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            response = await client.post(
                "/api/v1/vendors/",
                json=vendor_data
            )
        
        assert response.status_code == 409
        assert "Vendor profile already exists" in response.json()["detail"]

    async def test_update_vendor_success(self, client: AsyncClient, sample_vendor, mock_vendor_user):
        """Test successful vendor update."""
        # Update the vendor to belong to the mock user
        sample_vendor.user_id = mock_vendor_user["user_id"]
        
        update_data = {
            "business_name": "Updated Medical Supplies Ltd",
            "contact_phone": "+234-800-999-7777"
        }
        
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            response = await client.put(
                f"/api/v1/vendors/{sample_vendor.id}",
                json=update_data
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["business_name"] == update_data["business_name"]
        assert data["contact_phone"] == update_data["contact_phone"]

    async def test_update_vendor_unauthorized(self, client: AsyncClient, sample_vendor, mock_vendor_user):
        """Test vendor update by unauthorized user."""
        update_data = {
            "business_name": "Unauthorized Update"
        }
        
        with patch('shared.security.auth.get_current_user', return_value=mock_vendor_user):
            response = await client.put(
                f"/api/v1/vendors/{sample_vendor.id}",
                json=update_data
            )
        
        assert response.status_code == 403
        assert "You can only update your own vendor profile" in response.json()["detail"]

    async def test_update_vendor_admin_access(self, client: AsyncClient, sample_vendor, mock_admin_user):
        """Test vendor update by admin user."""
        update_data = {
            "verification_status": "verified"
        }
        
        with patch('shared.security.auth.get_current_user', return_value=mock_admin_user):
            response = await client.put(
                f"/api/v1/vendors/{sample_vendor.id}",
                json=update_data
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["verification_status"] == "verified"

    async def test_get_nearby_vendors_with_filters(self, client: AsyncClient, sample_vendor, mock_hospital_user):
        """Test nearby vendors search with various filters."""
        with patch('shared.security.auth.get_current_user', return_value=mock_hospital_user):
            response = await client.get(
                "/api/v1/vendors/nearby",
                params={
                    "latitude": 6.5244,
                    "longitude": 3.3792,
                    "radius_km": 100.0,
                    "business_type": "medical_supplier",
                    "verification_status": "pending",
                    "minimum_rating": 0.0,
                    "emergency_delivery": True,
                    "page": 1,
                    "page_size": 5
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 5
        # Verify that filters are applied (vendors should match criteria)
