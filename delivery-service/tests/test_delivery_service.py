import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.delivery_service import DeliveryService
from app.schemas.delivery import DeliveryCreate, DeliveryUpdate, DeliveryFilters, TrackingUpdate
from app.models.delivery import DeliveryStatus


class TestDeliveryService:
    """Test cases for DeliveryService."""

    @pytest.fixture
    def delivery_service(self):
        return DeliveryService()

    @pytest.mark.asyncio
    async def test_create_delivery(self, delivery_service: DeliveryService, 
                                 db_session: AsyncSession, sample_delivery_data):
        """Test creating a new delivery."""
        delivery_data = DeliveryCreate(**sample_delivery_data)
        
        delivery = await delivery_service.create_delivery(db_session, delivery_data)
        
        assert delivery is not None
        assert delivery.order_id == sample_delivery_data["order_id"]
        assert delivery.customer_id == sample_delivery_data["customer_id"]
        assert delivery.status == DeliveryStatus.PENDING
        assert delivery.distance_km is not None
        assert delivery.distance_km > 0

    @pytest.mark.asyncio
    async def test_get_delivery(self, delivery_service: DeliveryService, 
                              db_session: AsyncSession, sample_delivery_data):
        """Test getting a delivery by ID."""
        delivery_data = DeliveryCreate(**sample_delivery_data)
        created_delivery = await delivery_service.create_delivery(db_session, delivery_data)
        
        retrieved_delivery = await delivery_service.get_delivery(db_session, str(created_delivery.id))
        
        assert retrieved_delivery is not None
        assert retrieved_delivery.id == created_delivery.id
        assert retrieved_delivery.order_id == sample_delivery_data["order_id"]

    @pytest.mark.asyncio
    async def test_update_delivery(self, delivery_service: DeliveryService, 
                                 db_session: AsyncSession, sample_delivery_data):
        """Test updating a delivery."""
        delivery_data = DeliveryCreate(**sample_delivery_data)
        created_delivery = await delivery_service.create_delivery(db_session, delivery_data)
        
        update_data = DeliveryUpdate(
            status=DeliveryStatus.ASSIGNED,
            delivery_notes="Updated notes"
        )
        
        updated_delivery = await delivery_service.update_delivery(
            db_session, str(created_delivery.id), update_data
        )
        
        assert updated_delivery is not None
        assert updated_delivery.status == DeliveryStatus.ASSIGNED
        assert updated_delivery.delivery_notes == "Updated notes"

    @pytest.mark.asyncio
    async def test_get_deliveries_with_filters(self, delivery_service: DeliveryService, 
                                             db_session: AsyncSession, sample_delivery_data):
        """Test getting deliveries with filters."""
        # Create multiple deliveries
        delivery_data1 = DeliveryCreate(**sample_delivery_data)
        delivery_data2 = DeliveryCreate(**{**sample_delivery_data, "order_id": "order-456"})
        
        await delivery_service.create_delivery(db_session, delivery_data1)
        await delivery_service.create_delivery(db_session, delivery_data2)
        
        # Test filtering
        filters = DeliveryFilters(status=DeliveryStatus.PENDING)
        deliveries, total = await delivery_service.get_deliveries(db_session, filters)
        
        assert total == 2
        assert len(deliveries) == 2
        assert all(d.status == DeliveryStatus.PENDING for d in deliveries)

    @pytest.mark.asyncio
    async def test_add_tracking_update(self, delivery_service: DeliveryService, 
                                     db_session: AsyncSession, sample_delivery_data):
        """Test adding tracking update."""
        delivery_data = DeliveryCreate(**sample_delivery_data)
        created_delivery = await delivery_service.create_delivery(db_session, delivery_data)
        
        tracking_update = TrackingUpdate(
            status=DeliveryStatus.IN_TRANSIT,
            location_lat=6.5000,
            location_lng=3.3500,
            notes="Package picked up"
        )
        
        success = await delivery_service.add_tracking_update(
            db_session, str(created_delivery.id), tracking_update, "driver-123"
        )
        
        assert success is True
        
        # Verify tracking history
        tracking_history = await delivery_service.get_delivery_tracking(
            db_session, str(created_delivery.id)
        )
        
        assert len(tracking_history) >= 2  # Initial + new update
        assert any(t.status == DeliveryStatus.IN_TRANSIT for t in tracking_history)

    @pytest.mark.asyncio
    async def test_calculate_eta(self, delivery_service: DeliveryService):
        """Test ETA calculation."""
        eta_data = await delivery_service.calculate_eta(
            pickup_lat=6.5244,
            pickup_lng=3.3792,
            delivery_lat=6.4474,
            delivery_lng=3.3903,
            priority="NORMAL"
        )
        
        assert "distance_km" in eta_data
        assert "estimated_duration_minutes" in eta_data
        assert "estimated_pickup_time" in eta_data
        assert "estimated_delivery_time" in eta_data
        assert eta_data["distance_km"] > 0
        assert eta_data["estimated_duration_minutes"] > 0

    @pytest.mark.asyncio
    async def test_calculate_distance(self, delivery_service: DeliveryService):
        """Test distance calculation."""
        # Distance between two points in Lagos
        distance = await delivery_service._calculate_distance(
            6.5244, 3.3792,  # Victoria Island
            6.4474, 3.3903   # Ikeja
        )
        
        assert distance > 0
        assert distance < 50  # Should be reasonable distance within Lagos
