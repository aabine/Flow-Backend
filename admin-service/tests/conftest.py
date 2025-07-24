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
from app.main import app

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/test_oxygen_platform"

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
def admin_headers():
    """Headers for admin user authentication."""
    return {
        "X-User-ID": "admin-user-123",
        "X-User-Role": "admin"
    }


@pytest.fixture
def non_admin_headers():
    """Headers for non-admin user authentication."""
    return {
        "X-User-ID": "regular-user-123",
        "X-User-Role": "hospital"
    }


@pytest.fixture
def sample_analytics_data():
    """Sample analytics data for testing."""
    return {
        "order_analytics": {
            "total_orders": 150,
            "completed_orders": 135,
            "cancelled_orders": 10,
            "emergency_orders": 25,
            "completion_rate": 90.0,
            "average_order_value": 5000.0,
            "order_trends": [
                {"x": "2024-01-01", "y": 10},
                {"x": "2024-01-02", "y": 15},
                {"x": "2024-01-03", "y": 12}
            ]
        },
        "revenue_analytics": {
            "total_revenue": 750000.0,
            "platform_fees": 37500.0,
            "vendor_payouts": 712500.0,
            "revenue_by_period": [
                {"x": "2024-01-01", "y": 50000},
                {"x": "2024-01-02", "y": 75000},
                {"x": "2024-01-03", "y": 60000}
            ],
            "top_revenue_vendors": [
                {"vendor_id": "vendor-1", "revenue": 100000},
                {"vendor_id": "vendor-2", "revenue": 85000}
            ]
        },
        "user_analytics": {
            "total_hospitals": 45,
            "total_vendors": 25,
            "active_users_24h": 35,
            "new_registrations": 8,
            "user_growth_trend": [
                {"x": "2024-01-01", "y": 2},
                {"x": "2024-01-02", "y": 3},
                {"x": "2024-01-03", "y": 3}
            ],
            "geographic_distribution": [
                {"city": "Lagos", "user_count": 30},
                {"city": "Abuja", "user_count": 20}
            ]
        },
        "review_analytics": {
            "total_reviews": 120,
            "average_rating": 4.2,
            "rating_distribution": {"1": 2, "2": 5, "3": 15, "4": 45, "5": 53},
            "flagged_reviews": 3,
            "review_trends": [
                {"x": "2024-01-01", "y": 8},
                {"x": "2024-01-02", "y": 12},
                {"x": "2024-01-03", "y": 10}
            ]
        }
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "id": "user-123",
        "email": "test@example.com",
        "role": "hospital",
        "status": "active",
        "registration_date": "2024-01-01T00:00:00Z",
        "last_login": "2024-01-15T10:30:00Z",
        "order_count": 25,
        "total_spent": 125000.0,
        "rating": 4.5
    }


@pytest.fixture
def sample_alert_data():
    """Sample alert data for testing."""
    return {
        "id": "alert-123",
        "alert_type": "error",
        "severity": "high",
        "title": "Service Down",
        "message": "Payment service is not responding",
        "service_name": "payment-service",
        "status": "active",
        "created_at": "2024-01-15T10:00:00Z"
    }


@pytest.fixture
def mock_service_responses():
    """Mock responses from external services."""
    return {
        "user_service": {
            "users": [
                {
                    "id": "user-1",
                    "email": "hospital1@example.com",
                    "role": "hospital",
                    "status": "active"
                },
                {
                    "id": "user-2", 
                    "email": "vendor1@example.com",
                    "role": "vendor",
                    "status": "active"
                }
            ],
            "total": 2
        },
        "order_service": {
            "analytics": {
                "total_orders": 100,
                "completed_orders": 85,
                "trends": [{"date": "2024-01-01", "value": 10}]
            }
        },
        "payment_service": {
            "analytics": {
                "total_revenue": 500000,
                "platform_fees": 25000,
                "trends": [{"date": "2024-01-01", "value": 50000}]
            }
        }
    }
