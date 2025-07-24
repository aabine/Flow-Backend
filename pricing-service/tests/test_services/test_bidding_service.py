import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.bidding_service import BiddingService
from app.models.pricing import QuoteRequestStatus, BidStatus, AuctionStatus
from shared.models import CylinderSize


class TestBiddingService:
    
    @pytest.fixture
    def bidding_service(self):
        return BiddingService()
    
    @pytest.mark.asyncio
    async def test_create_quote_request_success(self, bidding_service, db_session, mock_httpx_client):
        """Test successful quote request creation."""
        
        quote_request = await bidding_service.create_quote_request(
            db=db_session,
            hospital_id="hospital-123",
            cylinder_size=CylinderSize.MEDIUM,
            quantity=50,
            delivery_address="123 Hospital Street, Lagos",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            required_delivery_date=datetime.utcnow() + timedelta(days=2),
            max_delivery_distance_km=25.0,
            additional_requirements="Urgent delivery",
            auction_duration_hours=48
        )
        
        assert quote_request is not None
        assert quote_request.hospital_id == "hospital-123"
        assert quote_request.cylinder_size == CylinderSize.MEDIUM
        assert quote_request.quantity == 50
        assert quote_request.status == QuoteRequestStatus.OPEN
        assert quote_request.auction is not None
    
    @pytest.mark.asyncio
    async def test_submit_bid_success(self, bidding_service, db_session, sample_quote_request, mock_httpx_client):
        """Test successful bid submission."""
        
        bid = await bidding_service.submit_bid(
            db=db_session,
            quote_request_id=sample_quote_request.id,
            vendor_id="vendor-123",
            unit_price=2800.0,
            delivery_fee=500.0,
            estimated_delivery_time_hours=24,
            notes="High quality cylinders"
        )
        
        assert bid is not None
        assert bid.quote_request_id == sample_quote_request.id
        assert bid.vendor_id == "vendor-123"
        assert bid.unit_price == 2800.0
        assert bid.total_price == (2800.0 * 50) + 500.0  # unit_price * quantity + delivery_fee
        assert bid.status == BidStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_submit_bid_duplicate_vendor(self, bidding_service, db_session, sample_quote_request, sample_bid):
        """Test bid submission by vendor who already has a bid."""
        
        with pytest.raises(ValueError, match="Vendor already has an active bid"):
            await bidding_service.submit_bid(
                db=db_session,
                quote_request_id=sample_quote_request.id,
                vendor_id="vendor-123",  # Same vendor as sample_bid
                unit_price=2700.0,
                delivery_fee=400.0,
                estimated_delivery_time_hours=20
            )
    
    @pytest.mark.asyncio
    async def test_submit_bid_expired_quote_request(self, bidding_service, db_session):
        """Test bid submission on expired quote request."""
        
        from app.models.pricing import QuoteRequest
        
        # Create expired quote request
        expired_quote = QuoteRequest(
            hospital_id="hospital-123",
            cylinder_size=CylinderSize.SMALL,
            quantity=25,
            delivery_address="Test Address",
            delivery_latitude=6.5244,
            delivery_longitude=3.3792,
            required_delivery_date=datetime.utcnow() + timedelta(days=1),
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Already expired
        )
        
        db_session.add(expired_quote)
        await db_session.commit()
        await db_session.refresh(expired_quote)
        
        with pytest.raises(ValueError, match="Quote request has expired"):
            await bidding_service.submit_bid(
                db=db_session,
                quote_request_id=expired_quote.id,
                vendor_id="vendor-456",
                unit_price=2500.0,
                delivery_fee=300.0,
                estimated_delivery_time_hours=18
            )
    
    @pytest.mark.asyncio
    async def test_get_quote_requests_success(self, bidding_service, db_session, sample_quote_request):
        """Test successful quote requests retrieval."""
        
        quote_requests, total = await bidding_service.get_quote_requests(
            db=db_session,
            hospital_id="hospital-123",
            page=1,
            size=20
        )
        
        assert total >= 1
        assert len(quote_requests) >= 1
        assert any(qr.id == sample_quote_request.id for qr in quote_requests)
    
    @pytest.mark.asyncio
    async def test_get_bids_for_quote_request(self, bidding_service, db_session, sample_quote_request, sample_bid):
        """Test getting bids for a quote request."""
        
        bids = await bidding_service.get_bids_for_quote_request(
            db=db_session,
            quote_request_id=sample_quote_request.id
        )
        
        assert len(bids) >= 1
        assert any(bid.id == sample_bid.id for bid in bids)
        assert all(bid.quote_request_id == sample_quote_request.id for bid in bids)
    
    @pytest.mark.asyncio
    async def test_rank_bids_success(self, bidding_service, db_session, sample_quote_request):
        """Test bid ranking algorithm."""
        
        from app.models.pricing import Bid
        
        # Create multiple bids with different characteristics
        bids_data = [
            {"vendor_id": "vendor-1", "unit_price": 2500.0, "delivery_fee": 300.0, "delivery_time": 12, "rating": 4.8, "distance": 5.0},
            {"vendor_id": "vendor-2", "unit_price": 2800.0, "delivery_fee": 200.0, "delivery_time": 24, "rating": 4.2, "distance": 15.0},
            {"vendor_id": "vendor-3", "unit_price": 2600.0, "delivery_fee": 400.0, "delivery_time": 18, "rating": 4.5, "distance": 10.0}
        ]
        
        for bid_data in bids_data:
            bid = Bid(
                quote_request_id=sample_quote_request.id,
                vendor_id=bid_data["vendor_id"],
                unit_price=bid_data["unit_price"],
                total_price=bid_data["unit_price"] * sample_quote_request.quantity + bid_data["delivery_fee"],
                delivery_fee=bid_data["delivery_fee"],
                estimated_delivery_time_hours=bid_data["delivery_time"],
                vendor_rating=bid_data["rating"],
                distance_km=bid_data["distance"]
            )
            db_session.add(bid)
        
        await db_session.commit()
        
        ranked_bids = await bidding_service.rank_bids(db_session, sample_quote_request.id)
        
        assert len(ranked_bids) == 3
        
        # Check that bids are ranked (highest score first)
        for i in range(len(ranked_bids) - 1):
            assert ranked_bids[i]["total_score"] >= ranked_bids[i + 1]["total_score"]
        
        # Check that all score components are present
        for ranked_bid in ranked_bids:
            assert "total_score" in ranked_bid
            assert "price_score" in ranked_bid
            assert "rating_score" in ranked_bid
            assert "distance_score" in ranked_bid
            assert "delivery_time_score" in ranked_bid
    
    @pytest.mark.asyncio
    async def test_accept_bid_success(self, bidding_service, db_session, sample_quote_request, sample_bid, mock_httpx_client):
        """Test successful bid acceptance."""
        
        accepted_bid = await bidding_service.accept_bid(
            db=db_session,
            bid_id=sample_bid.id,
            hospital_id="hospital-123"
        )
        
        assert accepted_bid.status == BidStatus.ACCEPTED
        assert accepted_bid.quote_request.status == QuoteRequestStatus.CLOSED
        
        # Check that auction is completed
        if accepted_bid.quote_request.auction:
            assert accepted_bid.quote_request.auction.status == AuctionStatus.COMPLETED
            assert accepted_bid.quote_request.auction.current_best_bid_id == accepted_bid.id
    
    @pytest.mark.asyncio
    async def test_accept_bid_unauthorized(self, bidding_service, db_session, sample_bid):
        """Test bid acceptance by unauthorized hospital."""
        
        with pytest.raises(ValueError, match="Unauthorized to accept this bid"):
            await bidding_service.accept_bid(
                db=db_session,
                bid_id=sample_bid.id,
                hospital_id="different-hospital-456"  # Different hospital
            )
    
    @pytest.mark.asyncio
    async def test_accept_bid_not_found(self, bidding_service, db_session):
        """Test accepting non-existent bid."""
        
        import uuid
        
        with pytest.raises(ValueError, match="Bid not found"):
            await bidding_service.accept_bid(
                db=db_session,
                bid_id=str(uuid.uuid4()),
                hospital_id="hospital-123"
            )
    
    @pytest.mark.asyncio
    async def test_get_quote_request_by_id_success(self, bidding_service, db_session, sample_quote_request):
        """Test getting quote request by ID."""
        
        quote_request = await bidding_service.get_quote_request_by_id(
            db_session, sample_quote_request.id
        )
        
        assert quote_request is not None
        assert quote_request.id == sample_quote_request.id
        assert quote_request.hospital_id == sample_quote_request.hospital_id
    
    @pytest.mark.asyncio
    async def test_get_quote_request_by_id_not_found(self, bidding_service, db_session):
        """Test getting non-existent quote request."""
        
        import uuid
        
        quote_request = await bidding_service.get_quote_request_by_id(
            db_session, str(uuid.uuid4())
        )
        
        assert quote_request is None
    
    @pytest.mark.asyncio
    async def test_auction_bid_tracking(self, bidding_service, db_session, sample_quote_request, sample_auction, mock_httpx_client):
        """Test that auction tracks bids correctly."""
        
        # Submit first bid
        bid1 = await bidding_service.submit_bid(
            db=db_session,
            quote_request_id=sample_quote_request.id,
            vendor_id="vendor-1",
            unit_price=3000.0,
            delivery_fee=500.0,
            estimated_delivery_time_hours=24
        )
        
        # Submit second bid with lower price
        bid2 = await bidding_service.submit_bid(
            db=db_session,
            quote_request_id=sample_quote_request.id,
            vendor_id="vendor-2",
            unit_price=2800.0,
            delivery_fee=400.0,
            estimated_delivery_time_hours=20
        )
        
        # Refresh auction to get updated data
        await db_session.refresh(sample_auction)
        
        # Check that auction tracks the best (lowest) bid
        assert sample_auction.current_best_bid_id == bid2.id
        assert sample_auction.current_best_price == bid2.total_price
        assert sample_auction.participant_count == 2
