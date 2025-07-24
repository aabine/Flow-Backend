from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.pricing import (
    QuoteRequest, Bid, Auction, PriceHistory, VendorPerformance,
    QuoteRequestStatus, BidStatus, AuctionStatus
)
from shared.models import CylinderSize


class PricingAnalyticsService:
    """Service for pricing analytics and reporting."""

    async def get_pricing_overview(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get pricing overview analytics."""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Total quote requests
        total_quotes_result = await db.execute(
            select(func.count(QuoteRequest.id)).where(
                QuoteRequest.created_at >= start_date
            )
        )
        total_quotes = total_quotes_result.scalar()
        
        # Active quote requests
        active_quotes_result = await db.execute(
            select(func.count(QuoteRequest.id)).where(
                and_(
                    QuoteRequest.status == QuoteRequestStatus.OPEN,
                    QuoteRequest.expires_at > datetime.utcnow()
                )
            )
        )
        active_quotes = active_quotes_result.scalar()
        
        # Total bids
        total_bids_result = await db.execute(
            select(func.count(Bid.id)).where(
                Bid.submitted_at >= start_date
            )
        )
        total_bids = total_bids_result.scalar()
        
        # Successful bids
        successful_bids_result = await db.execute(
            select(func.count(Bid.id)).where(
                and_(
                    Bid.submitted_at >= start_date,
                    Bid.status == BidStatus.ACCEPTED
                )
            )
        )
        successful_bids = successful_bids_result.scalar()
        
        # Average bid success rate
        success_rate = (successful_bids / total_bids * 100) if total_bids > 0 else 0
        
        # Average price per cylinder size
        avg_prices = await self._get_average_prices_by_cylinder_size(db, start_date)
        
        # Top performing vendors
        top_vendors = await self._get_top_vendors(db, start_date, limit=5)
        
        return {
            "period_days": days,
            "total_quote_requests": total_quotes,
            "active_quote_requests": active_quotes,
            "total_bids": total_bids,
            "successful_bids": successful_bids,
            "bid_success_rate": round(success_rate, 2),
            "average_prices_by_cylinder_size": avg_prices,
            "top_performing_vendors": top_vendors
        }

    async def get_price_trends(
        self,
        db: AsyncSession,
        cylinder_size: CylinderSize = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get price trends over time."""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        query = select(
            func.date(PriceHistory.recorded_at).label('date'),
            func.avg(PriceHistory.unit_price).label('avg_price'),
            func.min(PriceHistory.unit_price).label('min_price'),
            func.max(PriceHistory.unit_price).label('max_price'),
            func.count(PriceHistory.id).label('transaction_count')
        ).where(PriceHistory.recorded_at >= start_date)
        
        if cylinder_size:
            query = query.where(PriceHistory.cylinder_size == cylinder_size)
        
        query = query.group_by(func.date(PriceHistory.recorded_at)).order_by('date')
        
        result = await db.execute(query)
        trends = result.all()
        
        return {
            "cylinder_size": cylinder_size.value if cylinder_size else "all",
            "period_days": days,
            "trends": [
                {
                    "date": trend.date.isoformat(),
                    "average_price": float(trend.avg_price),
                    "min_price": float(trend.min_price),
                    "max_price": float(trend.max_price),
                    "transaction_count": trend.transaction_count
                }
                for trend in trends
            ]
        }

    async def get_vendor_performance_analytics(
        self,
        db: AsyncSession,
        vendor_id: str = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get vendor performance analytics."""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        query = select(VendorPerformance)
        
        if vendor_id:
            query = query.where(VendorPerformance.vendor_id == vendor_id)
        
        result = await db.execute(query)
        performances = result.scalars().all()
        
        # Get recent bid activity
        bid_activity_query = select(
            Bid.vendor_id,
            func.count(Bid.id).label('total_bids'),
            func.sum(func.case((Bid.status == BidStatus.ACCEPTED, 1), else_=0)).label('successful_bids'),
            func.avg(Bid.total_price).label('avg_bid_amount')
        ).where(Bid.submitted_at >= start_date)
        
        if vendor_id:
            bid_activity_query = bid_activity_query.where(Bid.vendor_id == vendor_id)
        
        bid_activity_query = bid_activity_query.group_by(Bid.vendor_id)
        
        bid_activity_result = await db.execute(bid_activity_query)
        bid_activities = {row.vendor_id: row for row in bid_activity_result.all()}
        
        vendor_analytics = []
        for performance in performances:
            bid_activity = bid_activities.get(performance.vendor_id)
            
            recent_success_rate = 0
            if bid_activity and bid_activity.total_bids > 0:
                recent_success_rate = (bid_activity.successful_bids / bid_activity.total_bids) * 100
            
            vendor_analytics.append({
                "vendor_id": performance.vendor_id,
                "overall_success_rate": round(performance.success_rate * 100, 2),
                "recent_success_rate": round(recent_success_rate, 2),
                "total_bids": performance.total_bids,
                "successful_bids": performance.successful_bids,
                "average_rating": performance.average_rating,
                "average_delivery_time_hours": performance.average_delivery_time_hours,
                "total_revenue": performance.total_revenue,
                "recent_bid_count": bid_activity.total_bids if bid_activity else 0,
                "recent_avg_bid_amount": float(bid_activity.avg_bid_amount) if bid_activity and bid_activity.avg_bid_amount else 0
            })
        
        return {
            "period_days": days,
            "vendor_count": len(vendor_analytics),
            "vendors": vendor_analytics
        }

    async def get_market_insights(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get market insights and competitive analysis."""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Price distribution by cylinder size
        price_distribution = await self._get_price_distribution(db, start_date)
        
        # Competition intensity (average bids per quote request)
        competition_result = await db.execute(
            select(
                func.avg(
                    select(func.count(Bid.id))
                    .where(Bid.quote_request_id == QuoteRequest.id)
                    .scalar_subquery()
                ).label('avg_bids_per_request')
            ).where(QuoteRequest.created_at >= start_date)
        )
        avg_competition = competition_result.scalar() or 0
        
        # Geographic distribution
        geographic_distribution = await self._get_geographic_distribution(db, start_date)
        
        # Delivery time analysis
        delivery_time_analysis = await self._get_delivery_time_analysis(db, start_date)
        
        return {
            "period_days": days,
            "average_bids_per_request": round(float(avg_competition), 2),
            "price_distribution": price_distribution,
            "geographic_distribution": geographic_distribution,
            "delivery_time_analysis": delivery_time_analysis
        }

    async def _get_average_prices_by_cylinder_size(
        self,
        db: AsyncSession,
        start_date: datetime
    ) -> Dict[str, float]:
        """Get average prices by cylinder size."""
        
        result = await db.execute(
            select(
                PriceHistory.cylinder_size,
                func.avg(PriceHistory.unit_price).label('avg_price')
            ).where(PriceHistory.recorded_at >= start_date)
            .group_by(PriceHistory.cylinder_size)
        )
        
        return {
            row.cylinder_size.value: round(float(row.avg_price), 2)
            for row in result.all()
        }

    async def _get_top_vendors(
        self,
        db: AsyncSession,
        start_date: datetime,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get top performing vendors."""
        
        result = await db.execute(
            select(
                VendorPerformance.vendor_id,
                VendorPerformance.success_rate,
                VendorPerformance.average_rating,
                VendorPerformance.total_revenue,
                func.count(Bid.id).label('recent_bids')
            ).join(
                Bid, Bid.vendor_id == VendorPerformance.vendor_id
            ).where(
                Bid.submitted_at >= start_date
            ).group_by(
                VendorPerformance.vendor_id,
                VendorPerformance.success_rate,
                VendorPerformance.average_rating,
                VendorPerformance.total_revenue
            ).order_by(
                desc(VendorPerformance.success_rate),
                desc(VendorPerformance.average_rating)
            ).limit(limit)
        )
        
        return [
            {
                "vendor_id": row.vendor_id,
                "success_rate": round(row.success_rate * 100, 2),
                "average_rating": row.average_rating,
                "total_revenue": row.total_revenue,
                "recent_bids": row.recent_bids
            }
            for row in result.all()
        ]

    async def _get_price_distribution(
        self,
        db: AsyncSession,
        start_date: datetime
    ) -> Dict[str, Any]:
        """Get price distribution statistics."""
        
        result = await db.execute(
            select(
                PriceHistory.cylinder_size,
                func.min(PriceHistory.unit_price).label('min_price'),
                func.max(PriceHistory.unit_price).label('max_price'),
                func.avg(PriceHistory.unit_price).label('avg_price'),
                func.percentile_cont(0.5).within_group(PriceHistory.unit_price).label('median_price')
            ).where(PriceHistory.recorded_at >= start_date)
            .group_by(PriceHistory.cylinder_size)
        )
        
        return {
            row.cylinder_size.value: {
                "min_price": float(row.min_price),
                "max_price": float(row.max_price),
                "avg_price": round(float(row.avg_price), 2),
                "median_price": round(float(row.median_price), 2)
            }
            for row in result.all()
        }

    async def _get_geographic_distribution(
        self,
        db: AsyncSession,
        start_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get geographic distribution of orders."""
        
        # This would need to be enhanced with proper geographic data
        # For now, return a placeholder
        return [
            {"location": "Lagos", "order_count": 45, "avg_price": 2500.0},
            {"location": "Abuja", "order_count": 32, "avg_price": 2800.0},
            {"location": "Port Harcourt", "order_count": 28, "avg_price": 2600.0}
        ]

    async def _get_delivery_time_analysis(
        self,
        db: AsyncSession,
        start_date: datetime
    ) -> Dict[str, Any]:
        """Get delivery time analysis."""
        
        result = await db.execute(
            select(
                func.avg(Bid.estimated_delivery_time_hours).label('avg_delivery_time'),
                func.min(Bid.estimated_delivery_time_hours).label('min_delivery_time'),
                func.max(Bid.estimated_delivery_time_hours).label('max_delivery_time')
            ).where(
                and_(
                    Bid.submitted_at >= start_date,
                    Bid.status == BidStatus.ACCEPTED
                )
            )
        )
        
        row = result.first()
        
        return {
            "average_delivery_time_hours": round(float(row.avg_delivery_time), 1) if row.avg_delivery_time else 0,
            "min_delivery_time_hours": row.min_delivery_time or 0,
            "max_delivery_time_hours": row.max_delivery_time or 0
        }
