import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import Base
from main import app

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/test_inventory_db"

# Create test engine
test_engine = create_async_engine(TEST_DATABASE_URL, echo=True)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_database():
    """Set up test database."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_database):
    """Create a test database session."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def client():
    """Create a test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def vendor_headers():
    """Headers for vendor user authentication."""
    return {
        "X-User-ID": "vendor-123",
        "X-User-Role": "vendor"
    }


@pytest.fixture
def hospital_headers():
    """Headers for hospital user authentication."""
    return {
        "X-User-ID": "hospital-123",
        "X-User-Role": "hospital"
    }


@pytest.fixture
def admin_headers():
    """Headers for admin user authentication."""
    return {
        "X-User-ID": "admin-123",
        "X-User-Role": "admin"
    }


@pytest.fixture
def sample_inventory_data():
    """Sample inventory data for testing."""
    return {
        "location_id": "location-123",
        "cylinder_size": "SMALL",
        "total_quantity": 100,
        "available_quantity": 80,
        "reserved_quantity": 20,
        "low_stock_threshold": 10,
        "unit_price": 2500.0,
        "notes": "Test inventory item"
    }


@pytest.fixture
def sample_location_data():
    """Sample location data for testing."""
    return {
        "name": "Test Warehouse",
        "address": "123 Test Street, Lagos",
        "latitude": 6.5244,
        "longitude": 3.3792,
        "is_active": True
    }


@pytest.fixture
def sample_stock_movement_data():
    """Sample stock movement data for testing."""
    return {
        "inventory_id": "inventory-123",
        "movement_type": "IN",
        "quantity": 50,
        "reference_id": "purchase-order-123",
        "notes": "Stock replenishment"
    }


@pytest.fixture
def sample_reservation_data():
    """Sample reservation data for testing."""
    return {
        "inventory_id": "inventory-123",
        "order_id": "order-123",
        "quantity": 10,
        "expires_at": "2024-12-31T23:59:59Z"
    }


@pytest.fixture
def mock_websocket_service():
    """Mock WebSocket service for testing."""
    with patch('app.services.websocket_service.websocket_service') as mock:
        mock.broadcast_stock_update = AsyncMock()
        mock.broadcast_low_stock_alert = AsyncMock()
        mock.broadcast_reservation_update = AsyncMock()
        mock.broadcast_stock_movement = AsyncMock()
        yield mock


@pytest.fixture
def mock_event_service():
    """Mock event service for testing."""
    with patch('app.services.event_service.event_service') as mock:
        mock.emit_inventory_created = AsyncMock()
        mock.emit_stock_updated = AsyncMock()
        mock.emit_reservation_created = AsyncMock()
        mock.emit_low_stock_alert = AsyncMock()
        yield mock


@pytest.fixture
def mock_external_services():
    """Mock external service responses."""
    return {
        "location_service": {
            "distance": 15.5,
            "vendors": [
                {"vendor_id": "vendor-1", "distance": 10.2},
                {"vendor_id": "vendor-2", "distance": 15.5}
            ]
        },
        "order_service": {
            "order": {
                "id": "order-123",
                "status": "confirmed",
                "items": [{"inventory_id": "inventory-123", "quantity": 10}]
            }
        }
    }


@pytest.fixture
async def sample_inventory_item(db_session, sample_inventory_data):
    """Create a sample inventory item for testing."""
    from app.models.inventory import Inventory
    
    inventory = Inventory(
        vendor_id="vendor-123",
        **sample_inventory_data
    )
    
    db_session.add(inventory)
    await db_session.commit()
    await db_session.refresh(inventory)
    
    return inventory


@pytest.fixture
async def sample_inventory_location(db_session, sample_location_data):
    """Create a sample inventory location for testing."""
    from app.models.inventory import InventoryLocation
    
    location = InventoryLocation(
        vendor_id="vendor-123",
        **sample_location_data
    )
    
    db_session.add(location)
    await db_session.commit()
    await db_session.refresh(location)
    
    return location


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for external API calls."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
        
        yield mock_client
