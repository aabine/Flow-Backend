from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.cylinder import (
    Cylinder, CylinderQualityCheck, CylinderLifecycleState, CylinderCondition, QualityCheckStatus
)
from app.models.inventory import Inventory, CylinderStock, StockMovement
from app.schemas.cylinder import CylinderAllocationRequest, CylinderAllocationOption, CylinderAllocationResponse
from shared.models import CylinderSize

logger = logging.getLogger(__name__)


class CylinderAllocationService:
    """Advanced cylinder allocation service with intelligent algorithms."""

    def __init__(self):
        self.allocation_weights = {
            'distance': 0.4,
            'cost': 0.3,
            'quality': 0.2,
            'availability': 0.1
        }

    async def allocate_cylinders_advanced(
        self, 
        db: AsyncSession, 
        allocation_request: CylinderAllocationRequest
    ) -> CylinderAllocationResponse:
        """
        Advanced cylinder allocation using multi-criteria optimization.
        
        Considers:
        - Distance and delivery time
        - Cost optimization
        - Quality scores
        - Vendor reliability
        - Emergency readiness
        - Maintenance schedules
        """
        try:
            # Step 1: Find candidate cylinders
            candidate_cylinders = await self._find_candidate_cylinders(db, allocation_request)
            
            # Step 2: Group by vendor and location
            vendor_groups = await self._group_cylinders_by_location(db, candidate_cylinders)
            
            # Step 3: Calculate allocation options with scoring
            allocation_options = await self._calculate_allocation_options(
                db, vendor_groups, allocation_request
            )
            
            # Step 4: Rank and optimize options
            ranked_options = await self._rank_allocation_options(db, allocation_options, allocation_request)
            
            # Step 5: Select recommended option
            recommended_option = ranked_options[0] if ranked_options else None
            
            return CylinderAllocationResponse(
                order_id=allocation_request.order_id,
                allocation_options=ranked_options,
                recommended_option=recommended_option,
                total_options_found=len(ranked_options),
                search_criteria=allocation_request
            )

        except Exception as e:
            logger.error(f"Error in advanced cylinder allocation: {e}")
            raise

    async def _find_candidate_cylinders(
        self, 
        db: AsyncSession, 
        allocation_request: CylinderAllocationRequest
    ) -> List[Cylinder]:
        """Find cylinders that meet basic allocation criteria."""
        
        # Base query for available cylinders
        query = select(Cylinder).options(
            joinedload(Cylinder.inventory_location),
            selectinload(Cylinder.quality_checks),
            selectinload(Cylinder.maintenance_records)
        ).where(
            and_(
                Cylinder.cylinder_size == allocation_request.cylinder_size,
                Cylinder.lifecycle_state == CylinderLifecycleState.ACTIVE,
                Cylinder.is_available == True,
                Cylinder.current_order_id.is_(None),
                Cylinder.fill_level_percentage >= allocation_request.min_fill_percentage
            )
        )

        # Emergency readiness filter
        if allocation_request.is_emergency:
            query = query.where(Cylinder.is_emergency_ready == True)

        # Preferred vendor filter
        if allocation_request.preferred_vendor_id:
            query = query.where(Cylinder.vendor_id == allocation_request.preferred_vendor_id)

        # Quality requirements filter
        if allocation_request.quality_requirements:
            # Subquery for cylinders with recent passing quality checks
            quality_subquery = select(CylinderQualityCheck.cylinder_id).where(
                and_(
                    CylinderQualityCheck.overall_status == QualityCheckStatus.PASSED,
                    CylinderQualityCheck.check_date >= datetime.now(datetime.timezone.utc) - timedelta(days=90),
                    CylinderQualityCheck.check_type.in_(allocation_request.quality_requirements)
                )
            ).group_by(CylinderQualityCheck.cylinder_id).having(
                func.count(CylinderQualityCheck.id) >= len(allocation_request.quality_requirements)
            )
            
            query = query.where(Cylinder.id.in_(quality_subquery))

        # Condition filter (exclude damaged/unsafe cylinders)
        query = query.where(
            Cylinder.condition.in_([
                CylinderCondition.EXCELLENT,
                CylinderCondition.GOOD,
                CylinderCondition.FAIR
            ])
        )

        # Execute query
        result = await db.execute(query)
        return result.scalars().all()

    async def _group_cylinders_by_location(
        self, 
        db: AsyncSession, 
        cylinders: List[Cylinder]
    ) -> Dict[str, Dict[str, Any]]:
        """Group cylinders by vendor and inventory location."""
        
        vendor_groups = {}
        
        for cylinder in cylinders:
            vendor_id = str(cylinder.vendor_id)
            location_id = str(cylinder.inventory_location_id)
            
            if vendor_id not in vendor_groups:
                vendor_groups[vendor_id] = {}
            
            if location_id not in vendor_groups[vendor_id]:
                vendor_groups[vendor_id][location_id] = {
                    'cylinders': [],
                    'location': cylinder.inventory_location,
                    'vendor_id': vendor_id
                }
            
            vendor_groups[vendor_id][location_id]['cylinders'].append(cylinder)

        return vendor_groups

    async def _calculate_allocation_options(
        self, 
        db: AsyncSession, 
        vendor_groups: Dict[str, Dict[str, Any]], 
        allocation_request: CylinderAllocationRequest
    ) -> List[Dict[str, Any]]:
        """Calculate allocation options with detailed scoring."""
        
        allocation_options = []
        
        for vendor_id, locations in vendor_groups.items():
            for location_id, location_data in locations.items():
                cylinders = location_data['cylinders']
                location = location_data['location']
                
                # Check if we have enough cylinders
                if len(cylinders) < allocation_request.quantity:
                    continue
                
                # Calculate distance
                distance = self._calculate_distance(
                    float(location.latitude), float(location.longitude),
                    float(allocation_request.delivery_latitude), 
                    float(allocation_request.delivery_longitude)
                )
                
                # Skip if outside max distance
                if distance > allocation_request.max_distance_km:
                    continue
                
                # Select best cylinders using multi-criteria scoring
                selected_cylinders = await self._select_best_cylinders(
                    cylinders, allocation_request.quantity, allocation_request.is_emergency
                )
                
                # Calculate comprehensive metrics
                metrics = await self._calculate_option_metrics(
                    db, selected_cylinders, distance, allocation_request
                )
                
                allocation_option = {
                    'vendor_id': vendor_id,
                    'location_id': location_id,
                    'location': location,
                    'cylinders': selected_cylinders,
                    'distance_km': distance,
                    'metrics': metrics
                }
                
                allocation_options.append(allocation_option)

        return allocation_options

    async def _select_best_cylinders(
        self, 
        cylinders: List[Cylinder], 
        quantity: int, 
        is_emergency: bool
    ) -> List[Cylinder]:
        """Select the best cylinders using multi-criteria scoring."""
        
        # Score each cylinder
        scored_cylinders = []
        for cylinder in cylinders:
            score = self._calculate_cylinder_score(cylinder, is_emergency)
            scored_cylinders.append((cylinder, score))
        
        # Sort by score (highest first) and select top cylinders
        scored_cylinders.sort(key=lambda x: x[1], reverse=True)
        return [cylinder for cylinder, score in scored_cylinders[:quantity]]

    def _calculate_cylinder_score(self, cylinder: Cylinder, is_emergency: bool) -> float:
        """Calculate a comprehensive score for cylinder selection."""
        
        score = 0.0
        
        # Fill level score (0-30 points)
        fill_score = float(cylinder.fill_level_percentage) * 0.3
        score += fill_score
        
        # Condition score (0-25 points)
        condition_scores = {
            CylinderCondition.EXCELLENT: 25,
            CylinderCondition.GOOD: 20,
            CylinderCondition.FAIR: 10,
            CylinderCondition.POOR: 5,
            CylinderCondition.DAMAGED: 0,
            CylinderCondition.UNSAFE: 0
        }
        score += condition_scores.get(cylinder.condition, 0)
        
        # Age score (0-20 points) - newer cylinders get higher scores
        days_since_manufacture = (datetime.now(datetime.timezone.utc) - cylinder.manufacture_date).days
        age_score = max(0, 20 - (days_since_manufacture / 365) * 2)  # 2 points per year
        score += age_score
        
        # Maintenance score (0-15 points)
        if cylinder.last_inspection_date:
            days_since_inspection = (datetime.now(datetime.timezone.utc) - cylinder.last_inspection_date).days
            maintenance_score = max(0, 15 - (days_since_inspection / 30))  # Decrease over time
            score += maintenance_score
        
        # Emergency readiness bonus (0-10 points)
        if is_emergency and cylinder.is_emergency_ready:
            score += 10
        
        return score

    async def _calculate_option_metrics(
        self, 
        db: AsyncSession, 
        cylinders: List[Cylinder], 
        distance_km: Decimal, 
        allocation_request: CylinderAllocationRequest
    ) -> Dict[str, Any]:
        """Calculate comprehensive metrics for an allocation option."""
        
        # Basic metrics
        total_capacity = sum(float(c.capacity_liters) for c in cylinders)
        average_fill = sum(float(c.fill_level_percentage) for c in cylinders) / len(cylinders)
        
        # Cost calculation
        base_cost = self._calculate_base_cost(cylinders)
        delivery_cost = self._calculate_delivery_cost(distance_km, allocation_request.is_emergency)
        total_cost = base_cost + delivery_cost
        
        # Quality score
        quality_score = await self._calculate_quality_score(db, cylinders)
        
        # Delivery time estimation
        delivery_time = self._estimate_delivery_time(distance_km, allocation_request.is_emergency)
        
        # Reliability score (based on vendor history)
        reliability_score = await self._calculate_reliability_score(db, cylinders[0].vendor_id)
        
        return {
            'total_capacity_liters': total_capacity,
            'average_fill_percentage': average_fill,
            'base_cost': float(base_cost),
            'delivery_cost': float(delivery_cost),
            'total_cost': float(total_cost),
            'quality_score': quality_score,
            'delivery_time_minutes': delivery_time,
            'reliability_score': reliability_score,
            'cylinder_count': len(cylinders)
        }

    async def _rank_allocation_options(
        self, 
        db: AsyncSession, 
        allocation_options: List[Dict[str, Any]], 
        allocation_request: CylinderAllocationRequest
    ) -> List[CylinderAllocationOption]:
        """Rank allocation options using weighted scoring."""
        
        if not allocation_options:
            return []
        
        # Calculate composite scores
        for option in allocation_options:
            option['composite_score'] = self._calculate_composite_score(option, allocation_request)
        
        # Sort by composite score (highest first)
        allocation_options.sort(key=lambda x: x['composite_score'], reverse=True)
        
        # Convert to response format
        ranked_options = []
        for option in allocation_options:
            allocation_option = CylinderAllocationOption(
                vendor_id=option['vendor_id'],
                vendor_name=f"Vendor {option['vendor_id']}",  # TODO: Get actual vendor name
                inventory_location_id=option['location_id'],
                location_name=option['location']['location_name'],
                distance_km=option['distance_km'],
                available_cylinders=[str(c.id) for c in option['cylinders']],
                estimated_delivery_time=option['metrics']['delivery_time_minutes'],
                total_cost=Decimal(str(option['metrics']['total_cost'])),
                currency="NGN"
            )
            ranked_options.append(allocation_option)
        
        return ranked_options

    def _calculate_composite_score(
        self, 
        option: Dict[str, Any], 
        allocation_request: CylinderAllocationRequest
    ) -> float:
        """Calculate weighted composite score for ranking."""
        
        metrics = option['metrics']
        
        # Normalize scores (0-100)
        distance_score = max(0, 100 - float(option['distance_km']) * 2)  # Closer is better
        cost_score = max(0, 100 - metrics['total_cost'] / 10)  # Lower cost is better
        quality_score = metrics['quality_score']  # Already 0-100
        reliability_score = metrics['reliability_score']  # Already 0-100
        
        # Apply weights
        composite_score = (
            distance_score * self.allocation_weights['distance'] +
            cost_score * self.allocation_weights['cost'] +
            quality_score * self.allocation_weights['quality'] +
            reliability_score * self.allocation_weights['availability']
        )
        
        # Emergency bonus
        if allocation_request.is_emergency:
            composite_score *= 1.1  # 10% bonus for emergency-ready options
        
        return composite_score

    # Helper methods
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Decimal:
        """Calculate distance using Haversine formula."""
        from math import radians, cos, sin, asin, sqrt
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # Earth radius in km
        
        return Decimal(str(c * r))

    def _calculate_base_cost(self, cylinders: List[Cylinder]) -> Decimal:
        """Calculate base cost for cylinders."""
        return Decimal("150.0") * len(cylinders)  # 150 NGN per cylinder

    def _calculate_delivery_cost(self, distance_km: Decimal, is_emergency: bool) -> Decimal:
        """Calculate delivery cost based on distance and urgency."""
        base_delivery = distance_km * Decimal("8.0")  # 8 NGN per km
        if is_emergency:
            return base_delivery * Decimal("1.5")  # 50% surcharge for emergency
        return base_delivery

    def _estimate_delivery_time(self, distance_km: Decimal, is_emergency: bool) -> int:
        """Estimate delivery time in minutes."""
        base_time = float(distance_km) * 2.5  # 2.5 minutes per km
        if is_emergency:
            return max(30, int(base_time * 0.6))  # 40% faster for emergency
        return max(60, int(base_time))

    async def _calculate_quality_score(self, db: AsyncSession, cylinders: List[Cylinder]) -> float:
        """Calculate quality score based on recent quality checks."""
        total_score = 0.0
        
        for cylinder in cylinders:
            # Get recent quality checks
            recent_checks = [
                qc for qc in cylinder.quality_checks
                if qc.check_date >= datetime.now(datetime.timezone.utc) - timedelta(days=90)
            ]
            
            if recent_checks:
                passed_checks = sum(1 for qc in recent_checks if qc.overall_status == QualityCheckStatus.PASSED)
                cylinder_score = (passed_checks / len(recent_checks)) * 100
            else:
                cylinder_score = 70  # Default score if no recent checks
            
            total_score += cylinder_score
        
        return total_score / len(cylinders) if cylinders else 0.0

    async def _calculate_reliability_score(self, db: AsyncSession, vendor_id: str) -> float:
        """Calculate vendor reliability score based on vendor performance metrics."""
        try:
            # Import vendor models (assuming they're available via HTTP calls to pricing service)
            # For now, we'll calculate based on available inventory data and simulate vendor metrics

            # Base score
            reliability_score = 50.0

            # Factor 1: Inventory availability and consistency (30% weight)
            availability_score = await self._calculate_availability_score(db, vendor_id)
            reliability_score += availability_score * 0.3

            # Factor 2: Stock movement consistency (25% weight)
            consistency_score = await self._calculate_stock_consistency_score(db, vendor_id)
            reliability_score += consistency_score * 0.25

            # Factor 3: Response time and active status (20% weight)
            responsiveness_score = await self._calculate_responsiveness_score(db, vendor_id)
            reliability_score += responsiveness_score * 0.2

            # Factor 4: Quality metrics from cylinder checks (25% weight)
            quality_score = await self._calculate_vendor_quality_score(db, vendor_id)
            reliability_score += quality_score * 0.25

            # Ensure score is within valid range
            return max(0.0, min(100.0, reliability_score))

        except Exception as e:
            logger.error(f"Error calculating reliability score for vendor {vendor_id}: {e}")
            # Return a conservative default score on error
            return 75.0

    async def _calculate_availability_score(self, db: AsyncSession, vendor_id: str) -> float:
        """Calculate score based on inventory availability."""
        try:
            # Get vendor's inventory locations and stock levels
            result = await db.execute(
                select(Inventory, CylinderStock)
                .join(CylinderStock, Inventory.id == CylinderStock.inventory_id)
                .where(and_(
                    Inventory.vendor_id == vendor_id,
                    Inventory.is_active == True
                ))
            )

            inventories = result.fetchall()
            if not inventories:
                return 0.0

            # Calculate availability metrics
            total_locations = len(set(inv.Inventory.id for inv in inventories))
            locations_with_stock = len(set(
                inv.Inventory.id for inv in inventories
                if inv.CylinderStock.available_quantity > 0
            ))

            # Calculate stock adequacy (above minimum threshold)
            adequate_stock_count = sum(
                1 for inv in inventories
                if inv.CylinderStock.available_quantity > inv.CylinderStock.minimum_threshold
            )

            # Availability score based on active locations and stock levels
            location_score = (locations_with_stock / total_locations) * 50 if total_locations > 0 else 0
            stock_score = (adequate_stock_count / len(inventories)) * 50 if inventories else 0

            return location_score + stock_score

        except Exception as e:
            logger.error(f"Error calculating availability score: {e}")
            return 30.0

    async def _calculate_stock_consistency_score(self, db: AsyncSession, vendor_id: str) -> float:
        """Calculate score based on stock movement patterns and consistency."""
        try:
            # Get recent stock movements for this vendor (last 30 days)
            thirty_days_ago = datetime.now(datetime.timezone.utc) - timedelta(days=30)

            result = await db.execute(
                select(StockMovement)
                .join(CylinderStock, StockMovement.stock_id == CylinderStock.id)
                .join(Inventory, CylinderStock.inventory_id == Inventory.id)
                .where(and_(
                    Inventory.vendor_id == vendor_id,
                    StockMovement.created_at >= thirty_days_ago
                ))
                .order_by(StockMovement.created_at.desc())
            )

            movements = result.fetchall()
            if not movements:
                return 40.0  # Neutral score for no recent activity

            # Analyze movement patterns
            inbound_movements = [m for m in movements if m.movement_type in ['received', 'restocked']]
            outbound_movements = [m for m in movements if m.movement_type in ['sold', 'reserved']]

            # Score based on regular restocking patterns
            restocking_score = min(50.0, len(inbound_movements) * 5)  # Up to 50 points for regular restocking

            # Score based on order fulfillment (outbound activity)
            fulfillment_score = min(50.0, len(outbound_movements) * 2)  # Up to 50 points for active sales

            return restocking_score + fulfillment_score

        except Exception as e:
            logger.error(f"Error calculating stock consistency score: {e}")
            return 35.0

    async def _calculate_responsiveness_score(self, db: AsyncSession, vendor_id: str) -> float:
        """Calculate score based on vendor responsiveness and activity."""
        try:
            # Check if vendor has active inventory locations
            result = await db.execute(
                select(func.count(Inventory.id))
                .where(and_(
                    Inventory.vendor_id == vendor_id,
                    Inventory.is_active == True
                ))
            )

            active_locations = result.scalar() or 0

            # Base score for having active locations
            activity_score = min(60.0, active_locations * 15)  # Up to 60 points for multiple active locations

            # Check recent inventory updates (last 7 days)
            seven_days_ago = datetime.now(datetime.timezone.utc) - timedelta(days=7)
            result = await db.execute(
                select(func.count(Inventory.id))
                .where(and_(
                    Inventory.vendor_id == vendor_id,
                    Inventory.updated_at >= seven_days_ago
                ))
            )

            recent_updates = result.scalar() or 0
            update_score = min(40.0, recent_updates * 10)  # Up to 40 points for recent updates

            return activity_score + update_score

        except Exception as e:
            logger.error(f"Error calculating responsiveness score: {e}")
            return 45.0

    async def _calculate_vendor_quality_score(self, db: AsyncSession, vendor_id: str) -> float:
        """Calculate score based on quality of cylinders from this vendor."""
        try:
            # Get quality check results for cylinders from this vendor's inventory
            result = await db.execute(
                select(CylinderQualityCheck)
                .join(Cylinder, CylinderQualityCheck.cylinder_id == Cylinder.id)
                .join(Inventory, Cylinder.current_location_id == Inventory.id)
                .where(and_(
                    Inventory.vendor_id == vendor_id,
                    CylinderQualityCheck.check_date >= datetime.now(datetime.timezone.utc) - timedelta(days=90)
                ))
                .order_by(CylinderQualityCheck.check_date.desc())
                .limit(100)  # Limit to recent 100 checks
            )

            quality_checks = result.fetchall()
            if not quality_checks:
                return 60.0  # Neutral score if no quality data

            # Calculate quality metrics
            passed_checks = sum(
                1 for qc in quality_checks
                if qc.overall_status == QualityCheckStatus.PASSED
            )

            quality_rate = (passed_checks / len(quality_checks)) * 100

            # Bonus for excellent quality (>95%)
            if quality_rate > 95:
                return 100.0
            elif quality_rate > 85:
                return quality_rate
            else:
                # Penalty for poor quality
                return max(20.0, quality_rate * 0.8)

        except Exception as e:
            logger.error(f"Error calculating vendor quality score: {e}")
            return 55.0
