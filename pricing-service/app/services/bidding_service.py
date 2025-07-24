from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import httpx
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.pricing import (
    QuoteRequest, Bid, Auction, PriceHistory, VendorPerformance,
    QuoteRequestStatus, BidStatus, AuctionStatus
)
from app.core.config import get_settings
from shared.models import CylinderSize

settings = get_settings()


class BiddingService:
    """Service for managing competitive bidding and auctions."""
    
    def __init__(self):
        self.settings = settings

    async def create_quote_request(
        self,
        db: AsyncSession,
        hospital_id: str,
        cylinder_size: CylinderSize,
        quantity: int,
        delivery_address: str,
        delivery_latitude: float,
        delivery_longitude: float,
        required_delivery_date: datetime,
        max_delivery_distance_km: float = None,
        additional_requirements: str = None,
        auction_duration_hours: int = None
    ) -> QuoteRequest:
        """Create a new quote request with optional auction."""
        
        # Set defaults
        if max_delivery_distance_km is None:
            max_delivery_distance_km = self.settings.MAX_DELIVERY_DISTANCE_KM
        
        if auction_duration_hours is None:
            auction_duration_hours = self.settings.DEFAULT_AUCTION_DURATION_HOURS
        
        # Validate auction duration
        auction_duration_hours = max(
            self.settings.MIN_AUCTION_DURATION_HOURS,
            min(auction_duration_hours, self.settings.MAX_AUCTION_DURATION_HOURS)
        )
        
        # Calculate expiry time
        expires_at = datetime.utcnow() + timedelta(hours=auction_duration_hours)
        
        # Create quote request
        quote_request = QuoteRequest(
            hospital_id=hospital_id,
            cylinder_size=cylinder_size,
            quantity=quantity,
            delivery_address=delivery_address,
            delivery_latitude=delivery_latitude,
            delivery_longitude=delivery_longitude,
            required_delivery_date=required_delivery_date,
            max_delivery_distance_km=max_delivery_distance_km,
            additional_requirements=additional_requirements,
            expires_at=expires_at
        )
        
        db.add(quote_request)
        await db.commit()
        await db.refresh(quote_request)
        
        # Create auction if enabled
        auction = Auction(
            quote_request_id=quote_request.id,
            ends_at=expires_at
        )
        
        db.add(auction)
        await db.commit()
        await db.refresh(auction)
        
        # Notify eligible vendors
        await self._notify_eligible_vendors(db, quote_request)
        
        return quote_request

    async def submit_bid(
        self,
        db: AsyncSession,
        quote_request_id: str,
        vendor_id: str,
        unit_price: float,
        delivery_fee: float = 0.0,
        estimated_delivery_time_hours: int = 24,
        notes: str = None
    ) -> Bid:
        """Submit a bid for a quote request."""
        
        # Get quote request
        quote_request = await self.get_quote_request_by_id(db, quote_request_id)
        if not quote_request:
            raise ValueError("Quote request not found")
        
        if quote_request.status != QuoteRequestStatus.OPEN:
            raise ValueError("Quote request is not open for bidding")
        
        if quote_request.expires_at <= datetime.utcnow():
            raise ValueError("Quote request has expired")
        
        # Check if vendor already has a bid
        existing_bid = await db.execute(
            select(Bid).where(
                and_(
                    Bid.quote_request_id == quote_request_id,
                    Bid.vendor_id == vendor_id,
                    Bid.status != BidStatus.WITHDRAWN
                )
            )
        )
        existing_bid = existing_bid.scalar_one_or_none()
        
        if existing_bid:
            raise ValueError("Vendor already has an active bid for this quote request")
        
        # Get vendor performance data
        vendor_performance = await self._get_vendor_performance(db, vendor_id)
        vendor_rating = vendor_performance.average_rating if vendor_performance else None
        
        # Calculate distance from vendor to delivery location
        distance_km = await self._calculate_delivery_distance(
            vendor_id, quote_request.delivery_latitude, quote_request.delivery_longitude
        )
        
        if distance_km > quote_request.max_delivery_distance_km:
            raise ValueError("Delivery location is outside vendor's service area")
        
        # Calculate total price
        total_price = (unit_price * quote_request.quantity) + delivery_fee
        
        # Create bid
        bid = Bid(
            quote_request_id=quote_request_id,
            vendor_id=vendor_id,
            unit_price=unit_price,
            total_price=total_price,
            delivery_fee=delivery_fee,
            estimated_delivery_time_hours=estimated_delivery_time_hours,
            vendor_rating=vendor_rating,
            distance_km=distance_km,
            notes=notes
        )
        
        db.add(bid)
        await db.commit()
        await db.refresh(bid)
        
        # Update auction if exists
        await self._update_auction_with_new_bid(db, quote_request_id, bid)
        
        # Notify hospital of new bid
        await self._notify_new_bid(quote_request, bid)
        
        return bid

    async def get_quote_requests(
        self,
        db: AsyncSession,
        hospital_id: str = None,
        status: QuoteRequestStatus = None,
        cylinder_size: CylinderSize = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[QuoteRequest], int]:
        """Get quote requests with filtering."""
        
        query = select(QuoteRequest).options(
            selectinload(QuoteRequest.bids),
            selectinload(QuoteRequest.auction)
        )
        
        # Apply filters
        conditions = []
        if hospital_id:
            conditions.append(QuoteRequest.hospital_id == hospital_id)
        if status:
            conditions.append(QuoteRequest.status == status)
        if cylinder_size:
            conditions.append(QuoteRequest.cylinder_size == cylinder_size)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get total count
        count_query = select(func.count(QuoteRequest.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        query = query.offset((page - 1) * size).limit(size)
        query = query.order_by(desc(QuoteRequest.created_at))
        
        result = await db.execute(query)
        quote_requests = result.scalars().all()
        
        return quote_requests, total

    async def get_bids_for_quote_request(
        self,
        db: AsyncSession,
        quote_request_id: str,
        include_withdrawn: bool = False
    ) -> List[Bid]:
        """Get all bids for a quote request."""
        
        query = select(Bid).where(Bid.quote_request_id == quote_request_id)
        
        if not include_withdrawn:
            query = query.where(Bid.status != BidStatus.WITHDRAWN)
        
        query = query.order_by(Bid.total_price.asc())
        
        result = await db.execute(query)
        return result.scalars().all()

    async def rank_bids(
        self,
        db: AsyncSession,
        quote_request_id: str
    ) -> List[Dict[str, Any]]:
        """Rank bids using weighted scoring algorithm."""
        
        bids = await self.get_bids_for_quote_request(db, quote_request_id)
        if not bids:
            return []
        
        # Calculate scores for each bid
        ranked_bids = []
        
        # Get min/max values for normalization
        prices = [bid.total_price for bid in bids]
        ratings = [bid.vendor_rating or 0 for bid in bids]
        distances = [bid.distance_km or 0 for bid in bids]
        delivery_times = [bid.estimated_delivery_time_hours for bid in bids]
        
        min_price, max_price = min(prices), max(prices)
        min_rating, max_rating = min(ratings), max(ratings)
        min_distance, max_distance = min(distances), max(distances)
        min_delivery_time, max_delivery_time = min(delivery_times), max(delivery_times)
        
        for bid in bids:
            # Normalize scores (0-1, higher is better)
            price_score = 1 - ((bid.total_price - min_price) / (max_price - min_price)) if max_price > min_price else 1
            rating_score = ((bid.vendor_rating or 0) - min_rating) / (max_rating - min_rating) if max_rating > min_rating else 0
            distance_score = 1 - ((bid.distance_km or 0) - min_distance) / (max_distance - min_distance) if max_distance > min_distance else 1
            delivery_time_score = 1 - ((bid.estimated_delivery_time_hours - min_delivery_time) / (max_delivery_time - min_delivery_time)) if max_delivery_time > min_delivery_time else 1
            
            # Calculate weighted score
            total_score = (
                price_score * self.settings.PRICE_WEIGHT +
                rating_score * self.settings.RATING_WEIGHT +
                distance_score * self.settings.DISTANCE_WEIGHT +
                delivery_time_score * self.settings.DELIVERY_TIME_WEIGHT
            )
            
            ranked_bids.append({
                "bid": bid,
                "total_score": total_score,
                "price_score": price_score,
                "rating_score": rating_score,
                "distance_score": distance_score,
                "delivery_time_score": delivery_time_score
            })
        
        # Sort by total score (highest first)
        ranked_bids.sort(key=lambda x: x["total_score"], reverse=True)
        
        return ranked_bids

    async def accept_bid(
        self,
        db: AsyncSession,
        bid_id: str,
        hospital_id: str
    ) -> Bid:
        """Accept a bid and close the quote request."""
        
        # Get bid with quote request
        bid_result = await db.execute(
            select(Bid).options(selectinload(Bid.quote_request)).where(Bid.id == bid_id)
        )
        bid = bid_result.scalar_one_or_none()
        
        if not bid:
            raise ValueError("Bid not found")
        
        if bid.quote_request.hospital_id != hospital_id:
            raise ValueError("Unauthorized to accept this bid")
        
        if bid.quote_request.status != QuoteRequestStatus.OPEN:
            raise ValueError("Quote request is not open")
        
        # Update bid status
        bid.status = BidStatus.ACCEPTED
        
        # Close quote request
        bid.quote_request.status = QuoteRequestStatus.CLOSED
        
        # Reject other bids
        other_bids = await db.execute(
            select(Bid).where(
                and_(
                    Bid.quote_request_id == bid.quote_request_id,
                    Bid.id != bid_id,
                    Bid.status == BidStatus.PENDING
                )
            )
        )
        
        for other_bid in other_bids.scalars():
            other_bid.status = BidStatus.REJECTED
        
        # Close auction if exists
        if bid.quote_request.auction:
            bid.quote_request.auction.status = AuctionStatus.COMPLETED
            bid.quote_request.auction.current_best_bid_id = bid_id
            bid.quote_request.auction.current_best_price = bid.total_price
        
        await db.commit()
        
        # Record price history
        await self._record_price_history(db, bid)
        
        # Update vendor performance
        await self._update_vendor_performance(db, bid.vendor_id, True)
        
        # Notify all participants
        await self._notify_bid_accepted(bid)
        
        return bid

    async def get_quote_request_by_id(self, db: AsyncSession, quote_request_id: str) -> Optional[QuoteRequest]:
        """Get quote request by ID."""
        result = await db.execute(
            select(QuoteRequest).options(
                selectinload(QuoteRequest.bids),
                selectinload(QuoteRequest.auction)
            ).where(QuoteRequest.id == quote_request_id)
        )
        return result.scalar_one_or_none()

    async def _notify_eligible_vendors(self, db: AsyncSession, quote_request: QuoteRequest):
        """Notify eligible vendors about new quote request."""
        try:
            # Get vendors within delivery radius
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.settings.INVENTORY_SERVICE_URL}/vendors/nearby",
                    params={
                        "latitude": quote_request.delivery_latitude,
                        "longitude": quote_request.delivery_longitude,
                        "max_distance_km": quote_request.max_delivery_distance_km,
                        "cylinder_size": quote_request.cylinder_size.value,
                        "min_quantity": quote_request.quantity
                    }
                )

                if response.status_code == 200:
                    vendors = response.json().get("vendors", [])

                    # Send notifications via WebSocket
                    for vendor in vendors:
                        await self._send_vendor_notification(vendor["vendor_id"], {
                            "type": "new_quote_request",
                            "quote_request_id": quote_request.id,
                            "cylinder_size": quote_request.cylinder_size.value,
                            "quantity": quote_request.quantity,
                            "delivery_location": quote_request.delivery_address,
                            "expires_at": quote_request.expires_at.isoformat()
                        })

        except Exception as e:
            print(f"Error notifying vendors: {e}")

    async def _calculate_delivery_distance(
        self,
        vendor_id: str,
        delivery_latitude: float,
        delivery_longitude: float
    ) -> float:
        """Calculate delivery distance from vendor to delivery location."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.settings.LOCATION_SERVICE_URL}/distance",
                    params={
                        "vendor_id": vendor_id,
                        "destination_latitude": delivery_latitude,
                        "destination_longitude": delivery_longitude
                    }
                )

                if response.status_code == 200:
                    return response.json().get("distance_km", 0.0)

        except Exception as e:
            print(f"Error calculating distance: {e}")

        return 0.0

    async def _get_vendor_performance(self, db: AsyncSession, vendor_id: str) -> Optional[VendorPerformance]:
        """Get vendor performance metrics."""
        result = await db.execute(
            select(VendorPerformance).where(VendorPerformance.vendor_id == vendor_id)
        )
        return result.scalar_one_or_none()

    async def _update_auction_with_new_bid(self, db: AsyncSession, quote_request_id: str, bid: Bid):
        """Update auction with new bid information."""
        auction_result = await db.execute(
            select(Auction).where(Auction.quote_request_id == quote_request_id)
        )
        auction = auction_result.scalar_one_or_none()

        if auction and auction.status == AuctionStatus.ACTIVE:
            # Update current best bid if this is better
            if (auction.current_best_price is None or
                bid.total_price < auction.current_best_price):
                auction.current_best_bid_id = bid.id
                auction.current_best_price = bid.total_price

            # Increment participant count if this is vendor's first bid
            vendor_bid_count = await db.execute(
                select(func.count(Bid.id)).where(
                    and_(
                        Bid.quote_request_id == quote_request_id,
                        Bid.vendor_id == bid.vendor_id
                    )
                )
            )

            if vendor_bid_count.scalar() == 1:  # First bid from this vendor
                auction.participant_count += 1

            await db.commit()

    async def _notify_new_bid(self, quote_request: QuoteRequest, bid: Bid):
        """Notify hospital of new bid."""
        try:
            await self._send_hospital_notification(quote_request.hospital_id, {
                "type": "new_bid",
                "quote_request_id": quote_request.id,
                "bid_id": bid.id,
                "vendor_id": bid.vendor_id,
                "total_price": bid.total_price,
                "estimated_delivery_time": bid.estimated_delivery_time_hours
            })
        except Exception as e:
            print(f"Error notifying hospital: {e}")

    async def _record_price_history(self, db: AsyncSession, bid: Bid):
        """Record price history for analytics."""
        price_history = PriceHistory(
            vendor_id=bid.vendor_id,
            cylinder_size=bid.quote_request.cylinder_size,
            unit_price=bid.unit_price,
            quantity=bid.quote_request.quantity,
            total_value=bid.total_price,
            delivery_location=bid.quote_request.delivery_address,
            delivery_distance_km=bid.distance_km
        )

        db.add(price_history)
        await db.commit()

    async def _update_vendor_performance(self, db: AsyncSession, vendor_id: str, bid_accepted: bool):
        """Update vendor performance metrics."""
        performance = await self._get_vendor_performance(db, vendor_id)

        if not performance:
            performance = VendorPerformance(vendor_id=vendor_id)
            db.add(performance)

        performance.total_bids += 1
        if bid_accepted:
            performance.successful_bids += 1

        performance.success_rate = performance.successful_bids / performance.total_bids
        performance.last_active_date = datetime.utcnow()

        await db.commit()

    async def _send_vendor_notification(self, vendor_id: str, notification: Dict[str, Any]):
        """Send notification to vendor via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.settings.WEBSOCKET_SERVICE_URL}/notify/vendor/{vendor_id}",
                    json=notification
                )
        except Exception as e:
            print(f"Error sending vendor notification: {e}")

    async def _send_hospital_notification(self, hospital_id: str, notification: Dict[str, Any]):
        """Send notification to hospital via WebSocket."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.settings.WEBSOCKET_SERVICE_URL}/notify/hospital/{hospital_id}",
                    json=notification
                )
        except Exception as e:
            print(f"Error sending hospital notification: {e}")
