import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.database import Base
from app.main import app

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://user:password@localhost:5432/test_pricing_db"

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
def hospital_headers():
    """Headers for hospital user authentication."""
    return {
        "X-User-ID": "hospital-123",
        "X-User-Role": "hospital"
    }


@pytest.fixture
def vendor_headers():
    """Headers for vendor user authentication."""
    return {
        "X-User-ID": "vendor-123",
        "X-User-Role": "vendor"
    }


@pytest.fixture
def admin_headers():
    """Headers for admin user authentication."""
    return {
        "X-User-ID": "admin-123",
        "X-User-Role": "admin"
    }


@pytest.fixture
def sample_quote_request_data():
    """Sample quote request data for testing."""
    return {
        "cylinder_size": "MEDIUM",
        "quantity": 50,
        "delivery_address": "123 Hospital Street, Lagos",
        "delivery_latitude": 6.5244,
        "delivery_longitude": 3.3792,
        "required_delivery_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
        "max_delivery_distance_km": 25.0,
        "additional_requirements": "Urgent delivery required",
        "auction_duration_hours": 48
    }


@pytest.fixture
def sample_bid_data():
    """Sample bid data for testing."""
    return {
        "unit_price": 2800.0,
        "delivery_fee": 500.0,
        "estimated_delivery_time_hours": 24,
        "notes": "High quality cylinders with fast delivery"
    }


@pytest.fixture
async def sample_quote_request(db_session, sample_quote_request_data):
    """Create a sample quote request for testing."""
    from app.models.pricing import QuoteRequest
    from shared.models import CylinderSize
    
    quote_request = QuoteRequest(
        hospital_id="hospital-123",
        cylinder_size=CylinderSize.MEDIUM,
        quantity=sample_quote_request_data["quantity"],
        delivery_address=sample_quote_request_data["delivery_address"],
        delivery_latitude=sample_quote_request_data["delivery_latitude"],
        delivery_longitude=sample_quote_request_data["delivery_longitude"],
        required_delivery_date=datetime.fromisoformat(sample_quote_request_data["required_delivery_date"]),
        max_delivery_distance_km=sample_quote_request_data["max_delivery_distance_km"],
        additional_requirements=sample_quote_request_data["additional_requirements"],
        expires_at=datetime.utcnow() + timedelta(hours=48)
    )
    
    db_session.add(quote_request)
    await db_session.commit()
    await db_session.refresh(quote_request)
    
    return quote_request


@pytest.fixture
async def sample_bid(db_session, sample_quote_request, sample_bid_data):
    """Create a sample bid for testing."""
    from app.models.pricing import Bid
    
    bid = Bid(
        quote_request_id=sample_quote_request.id,
        vendor_id="vendor-123",
        unit_price=sample_bid_data["unit_price"],
        total_price=sample_bid_data["unit_price"] * sample_quote_request.quantity + sample_bid_data["delivery_fee"],
        delivery_fee=sample_bid_data["delivery_fee"],
        estimated_delivery_time_hours=sample_bid_data["estimated_delivery_time_hours"],
        vendor_rating=4.5,
        distance_km=15.2,
        notes=sample_bid_data["notes"]
    )
    
    db_session.add(bid)
    await db_session.commit()
    await db_session.refresh(bid)
    
    return bid


@pytest.fixture
async def sample_auction(db_session, sample_quote_request):
    """Create a sample auction for testing."""
    from app.models.pricing import Auction
    
    auction = Auction(
        quote_request_id=sample_quote_request.id,
        ends_at=datetime.utcnow() + timedelta(hours=48)
    )
    
    db_session.add(auction)
    await db_session.commit()
    await db_session.refresh(auction)
    
    return auction


@pytest.fixture
def mock_external_services():
    """Mock external service responses."""
    return {
        "inventory_service": {
            "vendors": [
                {
                    "vendor_id": "vendor-1",
                    "distance": 10.5,
                    "available_quantity": 100
                },
                {
                    "vendor_id": "vendor-2", 
                    "distance": 15.2,
                    "available_quantity": 75
                }
            ]
        },
        "location_service": {
            "distance_km": 15.2
        },
        "order_service": {
            "order": {
                "id": "order-123",
                "status": "created",
                "total_amount": 140500.0
            }
        },
        "websocket_service": {
            "success": True,
            "message": "Notification sent"
        }
    }


@pytest.fixture
def mock_httpx_client(mock_external_services):
    """Mock httpx client for external API calls."""
    with patch('httpx.AsyncClient') as mock_client:
        def mock_response(url, **kwargs):
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            
            if "inventory-service" in url:
                if "vendors/nearby" in url:
                    mock_resp.json.return_value = mock_external_services["inventory_service"]
                else:
                    mock_resp.json.return_value = {"success": True}
            elif "location-service" in url:
                mock_resp.json.return_value = mock_external_services["location_service"]
            elif "order-service" in url:
                mock_resp.json.return_value = mock_external_services["order_service"]
            elif "websocket-service" in url:
                mock_resp.json.return_value = mock_external_services["websocket_service"]
            else:
                mock_resp.json.return_value = {"success": True}
            
            return mock_resp
        
        mock_client.return_value.__aenter__.return_value.get.side_effect = mock_response
        mock_client.return_value.__aenter__.return_value.post.side_effect = mock_response
        
        yield mock_client


@pytest.fixture
def sample_vendor_performance_data():
    """Sample vendor performance data for testing."""
    return {
        "vendor_id": "vendor-123",
        "total_bids": 25,
        "successful_bids": 20,
        "success_rate": 0.8,
        "average_delivery_time_hours": 18.5,
        "average_rating": 4.3,
        "total_orders_completed": 18,
        "total_revenue": 450000.0
    }


@pytest.fixture
async def sample_vendor_performance(db_session, sample_vendor_performance_data):
    """Create sample vendor performance for testing."""
    from app.models.pricing import VendorPerformance
    
    performance = VendorPerformance(**sample_vendor_performance_data)
    
    db_session.add(performance)
    await db_session.commit()
    await db_session.refresh(performance)
    
    return performance


@pytest.fixture
def sample_price_history_data():
    """Sample price history data for testing."""
    return [
        {
            "vendor_id": "vendor-123",
            "cylinder_size": "MEDIUM",
            "unit_price": 2800.0,
            "quantity": 50,
            "total_value": 140000.0,
            "delivery_location": "Lagos",
            "delivery_distance_km": 15.2
        },
        {
            "vendor_id": "vendor-456",
            "cylinder_size": "MEDIUM",
            "unit_price": 2750.0,
            "quantity": 30,
            "total_value": 82500.0,
            "delivery_location": "Abuja",
            "delivery_distance_km": 8.5
        }
    ]


@pytest.fixture
async def sample_price_history(db_session, sample_price_history_data):
    """Create sample price history for testing."""
    from app.models.pricing import PriceHistory
    from shared.models import CylinderSize
    
    price_records = []
    for data in sample_price_history_data:
        record = PriceHistory(
            vendor_id=data["vendor_id"],
            cylinder_size=CylinderSize.MEDIUM,
            unit_price=data["unit_price"],
            quantity=data["quantity"],
            total_value=data["total_value"],
            delivery_location=data["delivery_location"],
            delivery_distance_km=data["delivery_distance_km"]
        )
        price_records.append(record)
        db_session.add(record)
    
    await db_session.commit()
    
    for record in price_records:
        await db_session.refresh(record)
    
    return price_records
