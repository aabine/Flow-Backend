from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.bidding_service import BiddingService
from app.services.analytics_service import PricingAnalyticsService
from app.schemas.pricing import (
    QuoteRequestCreate, QuoteRequestResponse, QuoteRequestUpdate,
    BidCreate, BidResponse, BidUpdate,
    AuctionResponse, PaginatedQuoteRequestResponse,
    PaginatedBidResponse, BidRankingResponse
)
from shared.models import APIResponse, UserRole, CylinderSize

router = APIRouter()
bidding_service = BiddingService()
analytics_service = PricingAnalyticsService()


async def get_current_user(
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_user_role: str = Header(..., alias="X-User-Role")
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    return {
        "user_id": x_user_id,
        "role": UserRole(x_user_role)
    }


# Quote Request Management Routes
@router.post("/quote-requests", response_model=APIResponse)
async def create_quote_request(
    quote_data: QuoteRequestCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new quote request (hospitals only)."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can create quote requests")

        quote_request = await bidding_service.create_quote_request(
            db=db,
            hospital_id=current_user["user_id"],
            cylinder_size=quote_data.cylinder_size,
            quantity=quote_data.quantity,
            delivery_address=quote_data.delivery_address,
            delivery_latitude=quote_data.delivery_latitude,
            delivery_longitude=quote_data.delivery_longitude,
            required_delivery_date=quote_data.required_delivery_date,
            max_delivery_distance_km=quote_data.max_delivery_distance_km,
            additional_requirements=quote_data.additional_requirements,
            auction_duration_hours=quote_data.auction_duration_hours
        )

        return APIResponse(
            success=True,
            message="Quote request created successfully",
            data={"quote_request_id": quote_request.id}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create quote request")


@router.get("/quote-requests", response_model=PaginatedQuoteRequestResponse)
async def get_quote_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    cylinder_size: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get quote requests with filtering."""
    try:
        # Hospitals can only see their own quote requests
        hospital_id = current_user["user_id"] if current_user["role"] == UserRole.HOSPITAL else None

        quote_requests, total = await bidding_service.get_quote_requests(
            db=db,
            hospital_id=hospital_id,
            status=status,
            cylinder_size=CylinderSize(cylinder_size) if cylinder_size else None,
            page=page,
            size=size
        )

        pages = (total + size - 1) // size

        return PaginatedQuoteRequestResponse(
            items=[QuoteRequestResponse.from_orm(qr) for qr in quote_requests],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch quote requests")


@router.get("/quote-requests/{quote_request_id}", response_model=QuoteRequestResponse)
async def get_quote_request(
    quote_request_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific quote request."""
    try:
        quote_request = await bidding_service.get_quote_request_by_id(db, quote_request_id)
        if not quote_request:
            raise HTTPException(status_code=404, detail="Quote request not found")

        # Check permissions
        if (current_user["role"] == UserRole.HOSPITAL and
            quote_request.hospital_id != current_user["user_id"]):
            raise HTTPException(status_code=403, detail="Access denied")

        return QuoteRequestResponse.from_orm(quote_request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch quote request")


# Bidding Routes
@router.post("/quote-requests/{quote_request_id}/bids", response_model=APIResponse)
async def submit_bid(
    quote_request_id: str,
    bid_data: BidCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a bid for a quote request (vendors only)."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can submit bids")

        bid = await bidding_service.submit_bid(
            db=db,
            quote_request_id=quote_request_id,
            vendor_id=current_user["user_id"],
            unit_price=bid_data.unit_price,
            delivery_fee=bid_data.delivery_fee,
            estimated_delivery_time_hours=bid_data.estimated_delivery_time_hours,
            notes=bid_data.notes
        )

        return APIResponse(
            success=True,
            message="Bid submitted successfully",
            data={"bid_id": bid.id}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to submit bid")


@router.get("/quote-requests/{quote_request_id}/bids", response_model=List[BidResponse])
async def get_bids_for_quote_request(
    quote_request_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all bids for a quote request."""
    try:
        # Verify access to quote request
        quote_request = await bidding_service.get_quote_request_by_id(db, quote_request_id)
        if not quote_request:
            raise HTTPException(status_code=404, detail="Quote request not found")

        # Check permissions
        if (current_user["role"] == UserRole.HOSPITAL and
            quote_request.hospital_id != current_user["user_id"]):
            raise HTTPException(status_code=403, detail="Access denied")

        bids = await bidding_service.get_bids_for_quote_request(db, quote_request_id)

        return [BidResponse.from_orm(bid) for bid in bids]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch bids")


@router.get("/quote-requests/{quote_request_id}/bids/ranked", response_model=BidRankingResponse)
async def get_ranked_bids(
    quote_request_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get ranked bids for a quote request (hospitals only)."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can view ranked bids")

        # Verify access to quote request
        quote_request = await bidding_service.get_quote_request_by_id(db, quote_request_id)
        if not quote_request:
            raise HTTPException(status_code=404, detail="Quote request not found")

        if quote_request.hospital_id != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        ranked_bids = await bidding_service.rank_bids(db, quote_request_id)

        return BidRankingResponse(
            quote_request_id=quote_request_id,
            ranked_bids=ranked_bids
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to rank bids")


@router.post("/bids/{bid_id}/accept", response_model=APIResponse)
async def accept_bid(
    bid_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Accept a bid (hospitals only)."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can accept bids")

        bid = await bidding_service.accept_bid(
            db=db,
            bid_id=bid_id,
            hospital_id=current_user["user_id"]
        )

        # Trigger order creation in background
        background_tasks.add_task(
            create_order_from_accepted_bid,
            bid.id,
            bid.quote_request_id,
            current_user["user_id"]
        )

        return APIResponse(
            success=True,
            message="Bid accepted successfully",
            data={"bid_id": bid.id, "vendor_id": bid.vendor_id}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to accept bid")


# Vendor Routes
@router.get("/vendor/bids", response_model=PaginatedBidResponse)
async def get_vendor_bids(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor's bids."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(status_code=403, detail="Only vendors can access this endpoint")

        # This would need to be implemented in the bidding service
        # For now, return a placeholder
        return PaginatedBidResponse(
            items=[],
            total=0,
            page=page,
            size=size,
            pages=0
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch vendor bids")


# Analytics Routes
@router.get("/analytics/overview")
async def get_pricing_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get pricing overview analytics."""
    try:
        # Only admins and hospitals can access analytics
        if current_user["role"] not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        overview = await analytics_service.get_pricing_overview(db, days)
        return overview
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch pricing overview")


@router.get("/analytics/price-trends")
async def get_price_trends(
    cylinder_size: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get price trends analytics."""
    try:
        if current_user["role"] not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        cylinder_size_enum = CylinderSize(cylinder_size) if cylinder_size else None
        trends = await analytics_service.get_price_trends(db, cylinder_size_enum, days)
        return trends
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch price trends")


@router.get("/analytics/vendor-performance")
async def get_vendor_performance(
    vendor_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor performance analytics."""
    try:
        # Vendors can only see their own performance
        if current_user["role"] == UserRole.VENDOR:
            vendor_id = current_user["user_id"]
        elif current_user["role"] not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        performance = await analytics_service.get_vendor_performance_analytics(db, vendor_id, days)
        return performance
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch vendor performance")


@router.get("/analytics/market-insights")
async def get_market_insights(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get market insights and competitive analysis."""
    try:
        if current_user["role"] not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        insights = await analytics_service.get_market_insights(db, days)
        return insights
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch market insights")


# Integration Routes
async def create_order_from_accepted_bid(bid_id: str, quote_request_id: str, hospital_id: str):
    """Create order from accepted bid (background task)."""
    try:
        import httpx
        from app.core.config import get_settings

        settings = get_settings()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ORDER_SERVICE_URL}/orders/from-bid",
                json={
                    "bid_id": bid_id,
                    "quote_request_id": quote_request_id,
                    "hospital_id": hospital_id
                }
            )

            if response.status_code != 201:
                print(f"Failed to create order from bid {bid_id}: {response.text}")

    except Exception as e:
        print(f"Error creating order from bid {bid_id}: {e}")


# Health and Status Routes
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "pricing-service",
        "timestamp": datetime.utcnow().isoformat()
    }