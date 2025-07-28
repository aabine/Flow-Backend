import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
import os

from app.core.database import Base, get_db
from app.core.config import get_settings
from main import app

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/test_oxygen_platform"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

TestSessionLocal = sessionmaker(
    test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


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
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client."""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def mock_hospital_user():
    """Mock hospital user for testing."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "hospital@test.com",
        "role": "hospital",
        "hospital_id": "550e8400-e29b-41d4-a716-446655440001",
        "is_active": True,
        "is_verified": True
    }


@pytest.fixture
def mock_vendor_user():
    """Mock vendor user for testing."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440002",
        "email": "vendor@test.com",
        "role": "vendor",
        "is_active": True,
        "is_verified": True
    }


@pytest.fixture
def mock_admin_user():
    """Mock admin user for testing."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440003",
        "email": "admin@test.com",
        "role": "admin",
        "is_active": True,
        "is_verified": True
    }


@pytest.fixture
def sample_vendor_data():
    """Sample vendor data for testing."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440002",
        "business_name": "Test Medical Supplies Ltd",
        "business_registration_number": "RC123456",
        "tax_identification_number": "TIN123456",
        "contact_person": "John Doe",
        "contact_phone": "+234-800-123-4567",
        "contact_email": "contact@testmedical.com",
        "business_address": "123 Medical Street",
        "business_city": "Lagos",
        "business_state": "Lagos",
        "business_country": "Nigeria",
        "postal_code": "100001",
        "business_type": "medical_supplier",
        "years_in_business": 5,
        "license_number": "LIC123456",
        "emergency_contact": "+234-800-999-8888",
        "emergency_surcharge_percentage": 15.0,
        "minimum_order_value": 1000.0
    }


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "product_code": "OXY-MED-001",
        "product_name": "Medical Oxygen Cylinder - Medium",
        "product_category": "oxygen_cylinder",
        "product_subcategory": "portable",
        "cylinder_size": "medium",
        "capacity_liters": 10.0,
        "pressure_bar": 200.0,
        "gas_type": "medical_oxygen",
        "purity_percentage": 99.5,
        "weight_kg": 15.0,
        "material": "Steel",
        "color": "Green",
        "description": "High-quality medical oxygen cylinder for hospital use",
        "usage_instructions": "Connect to oxygen delivery system as per medical protocols",
        "safety_information": "Handle with care, store in upright position",
        "minimum_order_quantity": 1,
        "maximum_order_quantity": 50,
        "base_price": 5000.0,
        "currency": "NGN",
        "vendor_product_code": "TMD-OXY-MED-001",
        "manufacturer": "Test Medical Devices",
        "brand": "OxyPure",
        "model_number": "OP-MED-10L",
        "requires_special_handling": False,
        "hazardous_material": False,
        "storage_requirements": "Store in cool, dry place",
        "shelf_life_days": 1825
    }


@pytest.fixture
def sample_pricing_tier_data():
    """Sample pricing tier data for testing."""
    return {
        "tier_name": "Standard Pricing",
        "unit_price": 5000.0,
        "currency": "NGN",
        "minimum_quantity": 1,
        "maximum_quantity": 10,
        "delivery_fee": 500.0,
        "setup_fee": 0.0,
        "handling_fee": 100.0,
        "emergency_surcharge": 750.0,
        "bulk_discount_percentage": 5.0,
        "loyalty_discount_percentage": 2.0,
        "seasonal_discount_percentage": 0.0,
        "payment_terms": "net_30",
        "minimum_order_value": 5000.0,
        "cancellation_policy": "24 hours notice required",
        "pricing_notes": "Standard pricing for medical oxygen cylinders"
    }


@pytest.fixture
def sample_service_area_data():
    """Sample service area data for testing."""
    return {
        "area_name": "Lagos Metropolitan Area",
        "area_type": "radius",
        "center_latitude": 6.5244,
        "center_longitude": 3.3792,
        "radius_km": 50.0,
        "state": "Lagos",
        "cities": ["Lagos", "Ikeja", "Victoria Island"],
        "delivery_fee": 1000.0,
        "minimum_order_value": 5000.0,
        "estimated_delivery_time_hours": 4,
        "emergency_delivery_available": True,
        "emergency_delivery_time_hours": 2
    }
