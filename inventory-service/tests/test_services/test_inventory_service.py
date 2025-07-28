import pytest
from unittest.mock import AsyncMock, patch
import uuid
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.inventory_service import InventoryService
from app.schemas.inventory import InventoryCreate, StockAdjustment, StockReservationCreate
from app.models.inventory import Inventory, StockMovement, StockReservation
from shared.models import CylinderSize


class TestInventoryService:
    
    @pytest.fixture
    def inventory_service(self):
        return InventoryService()
    
    @pytest.mark.asyncio
    async def test_create_inventory_success(self, inventory_service, db_session, sample_inventory_data):
        """Test successful inventory creation."""
        
        inventory_data = InventoryCreate(**sample_inventory_data)
        
        inventory = await inventory_service.create_inventory(
            db_session, inventory_data, "vendor-123"
        )
        
        assert inventory is not None
        assert inventory.vendor_id == "vendor-123"
        assert inventory.cylinder_size == CylinderSize.SMALL
        assert inventory.total_quantity == 100
        assert inventory.available_quantity == 80
    
    @pytest.mark.asyncio
    async def test_create_inventory_invalid_quantities(self, inventory_service, db_session, sample_inventory_data):
        """Test inventory creation with invalid quantities."""
        
        # Test negative total quantity
        invalid_data = sample_inventory_data.copy()
        invalid_data["total_quantity"] = -10
        
        inventory_data = InventoryCreate(**invalid_data)
        
        with pytest.raises(ValueError, match="Total quantity must be positive"):
            await inventory_service.create_inventory(
                db_session, inventory_data, "vendor-123"
            )
    
    @pytest.mark.asyncio
    async def test_get_inventory_by_id_success(self, inventory_service, db_session, sample_inventory_item):
        """Test successful inventory retrieval by ID."""
        
        inventory = await inventory_service.get_inventory_by_id(
            db_session, str(sample_inventory_item.id)
        )
        
        assert inventory is not None
        assert inventory.id == sample_inventory_item.id
        assert inventory.vendor_id == sample_inventory_item.vendor_id
    
    @pytest.mark.asyncio
    async def test_get_inventory_by_id_not_found(self, inventory_service, db_session):
        """Test inventory retrieval with non-existent ID."""
        
        inventory = await inventory_service.get_inventory_by_id(
            db_session, str(uuid.uuid4())
        )
        
        assert inventory is None
    
    @pytest.mark.asyncio
    async def test_adjust_stock_increase(self, inventory_service, db_session, sample_inventory_item):
        """Test stock adjustment - increase."""
        
        adjustment = StockAdjustment(
            adjustment_type="increase",
            quantity=20,
            notes="Stock replenishment"
        )
        
        original_quantity = sample_inventory_item.available_quantity
        
        updated_inventory = await inventory_service.adjust_stock(
            db_session, str(sample_inventory_item.id), adjustment, "vendor-123"
        )
        
        assert updated_inventory.available_quantity == original_quantity + 20
        assert updated_inventory.total_quantity == sample_inventory_item.total_quantity + 20
    
    @pytest.mark.asyncio
    async def test_adjust_stock_decrease(self, inventory_service, db_session, sample_inventory_item):
        """Test stock adjustment - decrease."""
        
        adjustment = StockAdjustment(
            adjustment_type="decrease",
            quantity=10,
            notes="Stock correction"
        )
        
        original_quantity = sample_inventory_item.available_quantity
        
        updated_inventory = await inventory_service.adjust_stock(
            db_session, str(sample_inventory_item.id), adjustment, "vendor-123"
        )
        
        assert updated_inventory.available_quantity == original_quantity - 10
        assert updated_inventory.total_quantity == sample_inventory_item.total_quantity - 10
    
    @pytest.mark.asyncio
    async def test_adjust_stock_insufficient_quantity(self, inventory_service, db_session, sample_inventory_item):
        """Test stock adjustment with insufficient quantity."""
        
        adjustment = StockAdjustment(
            adjustment_type="decrease",
            quantity=1000,  # More than available
            notes="Invalid decrease"
        )
        
        with pytest.raises(ValueError, match="Insufficient available quantity"):
            await inventory_service.adjust_stock(
                db_session, str(sample_inventory_item.id), adjustment, "vendor-123"
            )
    
    @pytest.mark.asyncio
    async def test_create_reservation_success(self, inventory_service, db_session, sample_inventory_item):
        """Test successful reservation creation."""
        
        reservation_data = StockReservationCreate(
            inventory_id=str(sample_inventory_item.id),
            order_id="order-123",
            quantity=10,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        reservation = await inventory_service.create_reservation(
            db_session, reservation_data, "hospital-123"
        )
        
        assert reservation is not None
        assert reservation.inventory_id == sample_inventory_item.id
        assert reservation.order_id == "order-123"
        assert reservation.quantity == 10
        assert reservation.status == "active"
    
    @pytest.mark.asyncio
    async def test_create_reservation_insufficient_stock(self, inventory_service, db_session, sample_inventory_item):
        """Test reservation creation with insufficient stock."""
        
        reservation_data = StockReservationCreate(
            inventory_id=str(sample_inventory_item.id),
            order_id="order-123",
            quantity=1000,  # More than available
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        with pytest.raises(ValueError, match="Insufficient available quantity"):
            await inventory_service.create_reservation(
                db_session, reservation_data, "hospital-123"
            )
    
    @pytest.mark.asyncio
    async def test_confirm_reservation_success(self, inventory_service, db_session, sample_inventory_item):
        """Test successful reservation confirmation."""
        
        # First create a reservation
        reservation_data = StockReservationCreate(
            inventory_id=str(sample_inventory_item.id),
            order_id="order-123",
            quantity=10,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        reservation = await inventory_service.create_reservation(
            db_session, reservation_data, "hospital-123"
        )
        
        # Then confirm it
        confirmed_reservation = await inventory_service.confirm_reservation(
            db_session, str(reservation.id), "hospital-123"
        )
        
        assert confirmed_reservation.status == "confirmed"
        
        # Check that stock was deducted
        updated_inventory = await inventory_service.get_inventory_by_id(
            db_session, str(sample_inventory_item.id)
        )
        assert updated_inventory.available_quantity == sample_inventory_item.available_quantity - 10
    
    @pytest.mark.asyncio
    async def test_cancel_reservation_success(self, inventory_service, db_session, sample_inventory_item):
        """Test successful reservation cancellation."""
        
        # First create a reservation
        reservation_data = StockReservationCreate(
            inventory_id=str(sample_inventory_item.id),
            order_id="order-123",
            quantity=10,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        reservation = await inventory_service.create_reservation(
            db_session, reservation_data, "hospital-123"
        )
        
        original_available = sample_inventory_item.available_quantity
        
        # Cancel the reservation
        success = await inventory_service.cancel_reservation(
            db_session, str(reservation.id), "hospital-123"
        )
        
        assert success is True
        
        # Check that reserved quantity was released
        updated_inventory = await inventory_service.get_inventory_by_id(
            db_session, str(sample_inventory_item.id)
        )
        assert updated_inventory.reserved_quantity == sample_inventory_item.reserved_quantity - 10
    
    @pytest.mark.asyncio
    async def test_get_low_stock_items(self, inventory_service, db_session):
        """Test getting low stock items."""
        
        # Create inventory with low stock
        low_stock_inventory = Inventory(
            vendor_id="vendor-123",
            location_id="location-123",
            cylinder_size=CylinderSize.SMALL,
            total_quantity=20,
            available_quantity=5,  # Below threshold
            reserved_quantity=0,
            low_stock_threshold=10,
            unit_price=2500.0
        )
        
        db_session.add(low_stock_inventory)
        await db_session.commit()
        
        low_stock_items = await inventory_service.get_low_stock_items(db_session, "vendor-123")
        
        assert len(low_stock_items) > 0
        assert any(item.available_quantity <= item.low_stock_threshold for item in low_stock_items)
    
    @pytest.mark.asyncio
    async def test_create_inventory_location_success(self, inventory_service, db_session, sample_location_data):
        """Test successful inventory location creation."""
        
        from app.schemas.inventory import InventoryLocationCreate
        
        location_data = InventoryLocationCreate(**sample_location_data)
        
        location = await inventory_service.create_inventory_location(
            db_session, location_data, "vendor-123"
        )
        
        assert location is not None
        assert location.vendor_id == "vendor-123"
        assert location.name == "Test Warehouse"
        assert location.is_active is True
    
    @pytest.mark.asyncio
    async def test_get_inventory_analytics(self, inventory_service, db_session, sample_inventory_item):
        """Test inventory analytics generation."""
        
        analytics = await inventory_service.get_inventory_analytics(db_session, "vendor-123")
        
        assert "total_inventory_items" in analytics
        assert "total_stock_value" in analytics
        assert "low_stock_items" in analytics
        assert "total_locations" in analytics
        assert analytics["total_inventory_items"] >= 1  # At least our sample item
    
    @pytest.mark.asyncio
    async def test_bulk_update_inventory_success(self, inventory_service, db_session, sample_inventory_item):
        """Test bulk inventory update."""
        
        from app.schemas.inventory import BulkStockUpdate, StockUpdateItem
        
        bulk_update = BulkStockUpdate(
            updates=[
                StockUpdateItem(
                    inventory_id=str(sample_inventory_item.id),
                    adjustment_type="increase",
                    quantity=10,
                    notes="Bulk update test"
                )
            ]
        )
        
        results = await inventory_service.bulk_update_inventory(
            db_session, bulk_update, "vendor-123"
        )
        
        assert results["success_count"] == 1
        assert results["failure_count"] == 0
        assert len(results["successful"]) == 1
