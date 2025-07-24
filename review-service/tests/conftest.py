import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
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
def sample_review_data():
    """Sample review data for testing."""
    return {
        "order_id": "123e4567-e89b-12d3-a456-426614174000",
        "rating": 5,
        "comment": "Excellent service!",
        "is_anonymous": False
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user_id": "123e4567-e89b-12d3-a456-426614174001",
        "role": "hospital"
    }
