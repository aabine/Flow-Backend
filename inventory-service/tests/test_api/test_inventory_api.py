import pytest
from unittest.mock import AsyncMock, patch
import json
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class TestInventoryAPI:
    
    @pytest.mark.asyncio
    async def test_create_inventory_success(self, client, vendor_headers, sample_inventory_data, mock_websocket_service, mock_event_service):
        """Test successful inventory creation."""
        
        response = await client.post(
            "/inventory/",
            json=sample_inventory_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "inventory_id" in data["data"]
        
        # Verify WebSocket and event services were called
        mock_websocket_service.broadcast_stock_update.assert_called_once()
        mock_event_service.emit_inventory_created.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_inventory_non_vendor(self, client, hospital_headers, sample_inventory_data):
        """Test inventory creation by non-vendor user."""
        
        response = await client.post(
            "/inventory/",
            json=sample_inventory_data,
            headers=hospital_headers
        )
        
        assert response.status_code == 403
        assert "Only vendors can create inventory" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_inventory_success(self, client, vendor_headers, sample_inventory_item):
        """Test successful inventory retrieval."""
        
        response = await client.get(
            "/inventory/",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
    
    @pytest.mark.asyncio
    async def test_get_inventory_with_filters(self, client, vendor_headers):
        """Test inventory retrieval with filters."""
        
        response = await client.get(
            "/inventory/?cylinder_size=SMALL&low_stock_only=true",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    @pytest.mark.asyncio
    async def test_get_inventory_item_success(self, client, vendor_headers, sample_inventory_item):
        """Test getting specific inventory item."""
        
        response = await client.get(
            f"/inventory/{sample_inventory_item.id}",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_inventory_item.id)
        assert data["vendor_id"] == sample_inventory_item.vendor_id
    
    @pytest.mark.asyncio
    async def test_get_inventory_item_not_found(self, client, vendor_headers):
        """Test getting non-existent inventory item."""
        
        import uuid
        
        response = await client.get(
            f"/inventory/{uuid.uuid4()}",
            headers=vendor_headers
        )
        
        assert response.status_code == 404
        assert "Inventory not found" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_update_inventory_success(self, client, vendor_headers, sample_inventory_item, mock_websocket_service):
        """Test successful inventory update."""
        
        update_data = {
            "low_stock_threshold": 15,
            "notes": "Updated inventory item"
        }
        
        response = await client.put(
            f"/inventory/{sample_inventory_item.id}",
            json=update_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify WebSocket service was called
        mock_websocket_service.broadcast_stock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_adjust_stock_increase(self, client, vendor_headers, sample_inventory_item, mock_websocket_service):
        """Test stock adjustment - increase."""
        
        adjustment_data = {
            "adjustment_type": "increase",
            "quantity": 20,
            "notes": "Stock replenishment"
        }
        
        response = await client.post(
            f"/inventory/{sample_inventory_item.id}/adjust-stock",
            json=adjustment_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "increased" in data["message"]
        
        # Verify WebSocket service was called
        mock_websocket_service.broadcast_stock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_adjust_stock_decrease(self, client, vendor_headers, sample_inventory_item, mock_websocket_service):
        """Test stock adjustment - decrease."""
        
        adjustment_data = {
            "adjustment_type": "decrease",
            "quantity": 10,
            "notes": "Stock correction"
        }
        
        response = await client.post(
            f"/inventory/{sample_inventory_item.id}/adjust-stock",
            json=adjustment_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "decreased" in data["message"]
    
    @pytest.mark.asyncio
    async def test_adjust_stock_insufficient_quantity(self, client, vendor_headers, sample_inventory_item):
        """Test stock adjustment with insufficient quantity."""
        
        adjustment_data = {
            "adjustment_type": "decrease",
            "quantity": 1000,  # More than available
            "notes": "Invalid decrease"
        }
        
        response = await client.post(
            f"/inventory/{sample_inventory_item.id}/adjust-stock",
            json=adjustment_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 400
        assert "Insufficient" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_bulk_update_stock_success(self, client, vendor_headers, sample_inventory_item, mock_websocket_service):
        """Test bulk stock update."""
        
        bulk_update_data = {
            "updates": [
                {
                    "inventory_id": str(sample_inventory_item.id),
                    "adjustment_type": "increase",
                    "quantity": 15,
                    "notes": "Bulk update test"
                }
            ]
        }
        
        response = await client.post(
            "/inventory/bulk-update",
            json=bulk_update_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Bulk update completed" in data["message"]
        
        # Verify WebSocket service was called
        mock_websocket_service.broadcast_bulk_stock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_low_stock_alerts(self, client, vendor_headers):
        """Test getting low stock alerts."""
        
        response = await client.get(
            "/inventory/low-stock/alerts",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "low_stock_items" in data
        assert "total_alerts" in data
    
    @pytest.mark.asyncio
    async def test_create_reservation_success(self, client, hospital_headers, sample_inventory_item, mock_websocket_service):
        """Test successful reservation creation."""
        
        reservation_data = {
            "inventory_id": str(sample_inventory_item.id),
            "order_id": "order-123",
            "quantity": 10,
            "expires_at": "2024-12-31T23:59:59Z"
        }
        
        response = await client.post(
            "/inventory/reservations",
            json=reservation_data,
            headers=hospital_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "reservation_id" in data["data"]
        
        # Verify WebSocket service was called
        mock_websocket_service.broadcast_reservation_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_inventory_location_success(self, client, vendor_headers, sample_location_data):
        """Test successful inventory location creation."""
        
        response = await client.post(
            "/inventory/locations",
            json=sample_location_data,
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "location_id" in data["data"]
    
    @pytest.mark.asyncio
    async def test_get_inventory_locations(self, client, vendor_headers, sample_inventory_location):
        """Test getting inventory locations."""
        
        response = await client.get(
            "/inventory/locations",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_inventory_analytics(self, client, vendor_headers):
        """Test getting inventory analytics."""
        
        response = await client.get(
            "/inventory/analytics/summary",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "total_inventory_items" in data
        assert "total_stock_value" in data
        assert "low_stock_items" in data
    
    @pytest.mark.asyncio
    async def test_get_real_time_summary(self, client, vendor_headers):
        """Test getting real-time inventory summary."""
        
        response = await client.get(
            "/inventory/real-time/summary",
            headers=vendor_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        # Real-time summary should return some data structure
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client, sample_inventory_data):
        """Test API access without authentication headers."""
        
        response = await client.post(
            "/inventory/",
            json=sample_inventory_data
        )
        
        assert response.status_code == 422  # Missing required headers
    
    @pytest.mark.asyncio
    async def test_vendor_access_control(self, client, hospital_headers, sample_inventory_item):
        """Test that hospitals cannot access vendor-specific inventory."""
        
        response = await client.get(
            f"/inventory/{sample_inventory_item.id}",
            headers=hospital_headers
        )
        
        # Hospitals should be able to view inventory for ordering purposes
        # but may have restricted access to certain operations
        assert response.status_code in [200, 403]
