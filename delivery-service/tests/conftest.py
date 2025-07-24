import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient
import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.core.database import get_db, Base
from app.core.config import get_settings

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create test session factory
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client."""
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def mock_current_user():
    """Mock current user for authentication."""
    return {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "role": "customer"
    }


@pytest.fixture
def sample_delivery_data():
    """Sample delivery data for testing."""
    return {
        "order_id": "order-123",
        "customer_id": "customer-123",
        "cylinder_size": "SMALL",
        "quantity": 2,
        "priority": "NORMAL",
        "pickup_address": "123 Pickup St, Lagos, Nigeria",
        "pickup_lat": 6.5244,
        "pickup_lng": 3.3792,
        "delivery_address": "456 Delivery Ave, Lagos, Nigeria",
        "delivery_lat": 6.4474,
        "delivery_lng": 3.3903,
        "delivery_fee": 25.0,
        "special_instructions": "Handle with care"
    }


@pytest.fixture
def sample_driver_data():
    """Sample driver data for testing."""
    return {
        "user_id": "driver-123",
        "driver_license": "DL123456789",
        "phone_number": "+2348012345678",
        "vehicle_type": "VAN",
        "vehicle_plate": "ABC-123-XY",
        "vehicle_capacity": 10
    }
