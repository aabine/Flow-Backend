from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
import logging
import math

from app.models.vendor import Vendor
from app.models.product import ProductCatalog
from app.models.pricing import PricingTier, PriceHistory
from app.schemas.pricing import (
    PriceComparisonRequest, PriceComparisonResponse, VendorPricingOption,
    BulkPricingRequest, BulkPricingResponse, BulkPricingOption, BulkPricingItem,
    PricingTierCreate, PricingTierUpdate, PricingTierResponse
)
from app.services.event_service import event_service

logger = logging.getLogger(__name__)


class PricingService:
    """Service for pricing management and comparison operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def compare_prices(self, comparison_request: PriceComparisonRequest) -> PriceComparisonResponse:
        """Compare prices across multiple vendors for specific products."""
        try:
            # Build base query
            query = select(ProductCatalog).options(
                joinedload(ProductCatalog.vendor),
                joinedload(ProductCatalog.pricing_tiers)
            )
            
            # Apply product filters
            filters = [
                ProductCatalog.is_active == True,
                ProductCatalog.approval_status == "approved",
                ProductCatalog.stock_status == "in_stock"
            ]
            
            if comparison_request.product_id:
                filters.append(ProductCatalog.id == comparison_request.product_id)
            
            if comparison_request.product_category:
                filters.append(ProductCatalog.product_category == comparison_request.product_category)
            
            if comparison_request.cylinder_size:
                filters.append(ProductCatalog.cylinder_size == comparison_request.cylinder_size)
            
            query = query.where(and_(*filters))
            
            # Execute query
            result = await self.db.execute(query)
            products = result.scalars().all()
            
            # Process pricing options
            pricing_options = []
            for product in products:
                # Check if vendor serves the location
                serves_location, distance = await self._check_vendor_serves_location(
                    product.vendor, comparison_request.latitude, comparison_request.longitude,
                    comparison_request.radius_km
                )
                
                if not serves_location:
                    continue
                
                # Get appropriate pricing tier
                pricing_tier = await self._get_best_pricing_tier(
                    product, comparison_request.quantity, comparison_request.include_emergency_pricing
                )
                
                if pricing_tier:
                    pricing_option = await self._create_vendor_pricing_option(
                        product, pricing_tier, comparison_request.quantity, distance
                    )
                    pricing_options.append(pricing_option)
            
            # Sort pricing options
            pricing_options = self._sort_pricing_options(pricing_options, comparison_request.sort_by)
            
            # Limit results
            if comparison_request.max_results:
                pricing_options = pricing_options[:comparison_request.max_results]
            
            # Find best options
            best_price_option = min(pricing_options, key=lambda x: x.total_price) if pricing_options else None
            fastest_delivery_option = min(pricing_options, key=lambda x: x.estimated_delivery_hours) if pricing_options else None
            highest_rated_option = max(pricing_options, key=lambda x: x.vendor_rating or 0) if pricing_options else None
            closest_vendor_option = min(pricing_options, key=lambda x: x.distance_km) if pricing_options else None
            
            # Create comparison summary
            comparison_summary = {
                "total_options": len(pricing_options),
                "price_range": {
                    "min": min(opt.total_price for opt in pricing_options) if pricing_options else None,
                    "max": max(opt.total_price for opt in pricing_options) if pricing_options else None,
                    "average": sum(opt.total_price for opt in pricing_options) / len(pricing_options) if pricing_options else None
                },
                "delivery_time_range": {
                    "min": min(opt.estimated_delivery_hours for opt in pricing_options) if pricing_options else None,
                    "max": max(opt.estimated_delivery_hours for opt in pricing_options) if pricing_options else None
                },
                "distance_range": {
                    "min": min(opt.distance_km for opt in pricing_options) if pricing_options else None,
                    "max": max(opt.distance_km for opt in pricing_options) if pricing_options else None
                }
            }
            
            return PriceComparisonResponse(
                options=pricing_options,
                best_price_option=best_price_option,
                fastest_delivery_option=fastest_delivery_option,
                highest_rated_option=highest_rated_option,
                closest_vendor_option=closest_vendor_option,
                comparison_summary=comparison_summary,
                search_criteria=comparison_request,
                total_vendors_found=len(pricing_options),
                search_timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error comparing prices: {e}")
            raise
    
    async def get_bulk_pricing(self, bulk_request: BulkPricingRequest) -> BulkPricingResponse:
        """Get bulk pricing for multiple products from vendors."""
        try:
            # Get all products requested
            product_ids = [item.get("product_id") for item in bulk_request.items if item.get("product_id")]
            
            query = select(ProductCatalog).options(
                joinedload(ProductCatalog.vendor),
                joinedload(ProductCatalog.pricing_tiers)
            ).where(
                and_(
                    ProductCatalog.id.in_(product_ids),
                    ProductCatalog.is_active == True,
                    ProductCatalog.approval_status == "approved"
                )
            )
            
            result = await self.db.execute(query)
            products = result.scalars().all()
            
            # Group products by vendor
            vendor_products = {}
            for product in products:
                # Check if vendor serves the location
                serves_location, distance = await self._check_vendor_serves_location(
                    product.vendor, bulk_request.latitude, bulk_request.longitude,
                    bulk_request.radius_km
                )
                
                if not serves_location:
                    continue
                
                vendor_id = str(product.vendor_id)
                if vendor_id not in vendor_products:
                    vendor_products[vendor_id] = {
                        "vendor": product.vendor,
                        "products": [],
                        "distance": distance
                    }
                vendor_products[vendor_id]["products"].append(product)
            
            # Calculate bulk pricing for each vendor
            bulk_options = []
            for vendor_id, vendor_data in vendor_products.items():
                vendor = vendor_data["vendor"]
                vendor_products_list = vendor_data["products"]
                distance = vendor_data["distance"]
                
                # Check if vendor has all requested products
                vendor_product_ids = {str(p.id) for p in vendor_products_list}
                has_all_products = all(
                    item.get("product_id") in vendor_product_ids 
                    for item in bulk_request.items
                )
                
                if not has_all_products:
                    continue
                
                # Calculate pricing for this vendor
                bulk_option = await self._calculate_bulk_pricing_for_vendor(
                    vendor, vendor_products_list, bulk_request.items, distance
                )
                
                if bulk_option:
                    bulk_options.append(bulk_option)
            
            # Sort by total price
            bulk_options.sort(key=lambda x: x.total_price)
            
            # Find best and recommended options
            best_price_option = bulk_options[0] if bulk_options else None
            recommended_option = self._get_recommended_bulk_option(bulk_options)
            
            return BulkPricingResponse(
                options=bulk_options,
                best_price_option=best_price_option,
                recommended_option=recommended_option,
                total_vendors_found=len(bulk_options),
                search_criteria=bulk_request
            )
            
        except Exception as e:
            logger.error(f"Error getting bulk pricing: {e}")
            raise

    async def create_pricing_tier(self, pricing_data: PricingTierCreate, vendor_user_id: str) -> PricingTierResponse:
        """Create a new pricing tier for a product."""
        try:
            # Get vendor by user ID
            vendor_query = select(Vendor).where(Vendor.user_id == vendor_user_id)
            vendor_result = await self.db.execute(vendor_query)
            vendor = vendor_result.scalar_one_or_none()

            if not vendor:
                raise ValueError("Vendor not found for user")

            # Verify product belongs to vendor
            product_query = select(ProductCatalog).where(
                and_(
                    ProductCatalog.id == pricing_data.product_id,
                    ProductCatalog.vendor_id == vendor.id
                )
            )
            product_result = await self.db.execute(product_query)
            product = product_result.scalar_one_or_none()

            if not product:
                raise ValueError("Product not found or does not belong to vendor")

            # Create pricing tier
            pricing_tier = PricingTier(
                vendor_id=vendor.id,
                product_id=pricing_data.product_id,
                service_area_id=pricing_data.service_area_id,
                tier_name=pricing_data.tier_name,
                unit_price=pricing_data.unit_price,
                currency=pricing_data.currency,
                minimum_quantity=pricing_data.minimum_quantity,
                maximum_quantity=pricing_data.maximum_quantity,
                delivery_fee=pricing_data.delivery_fee,
                setup_fee=pricing_data.setup_fee,
                handling_fee=pricing_data.handling_fee,
                emergency_surcharge=pricing_data.emergency_surcharge,
                bulk_discount_percentage=pricing_data.bulk_discount_percentage,
                loyalty_discount_percentage=pricing_data.loyalty_discount_percentage,
                seasonal_discount_percentage=pricing_data.seasonal_discount_percentage,
                payment_terms=pricing_data.payment_terms,
                minimum_order_value=pricing_data.minimum_order_value,
                cancellation_policy=pricing_data.cancellation_policy,
                pricing_notes=pricing_data.pricing_notes,
                effective_from=pricing_data.effective_from or datetime.utcnow(),
                effective_until=pricing_data.effective_until
            )

            self.db.add(pricing_tier)
            await self.db.commit()
            await self.db.refresh(pricing_tier)

            # Publish price update event
            await event_service.publish_price_update(
                str(vendor.id),
                str(product.id),
                0.0,  # No old price for new tier
                float(pricing_tier.unit_price),
                str(pricing_tier.id)
            )

            return await self._pricing_tier_to_response(pricing_tier)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating pricing tier: {e}")
            raise

    async def get_vendor_pricing_tiers(self, vendor_id: Optional[str] = None,
                                     product_id: Optional[str] = None,
                                     active_only: bool = True) -> List[PricingTierResponse]:
        """Get pricing tiers for a vendor."""
        try:
            query = select(PricingTier)

            filters = []
            if vendor_id:
                filters.append(PricingTier.vendor_id == vendor_id)

            if product_id:
                filters.append(PricingTier.product_id == product_id)

            if active_only:
                filters.append(PricingTier.is_active == True)
                filters.append(
                    or_(
                        PricingTier.effective_until.is_(None),
                        PricingTier.effective_until > datetime.utcnow()
                    )
                )

            if filters:
                query = query.where(and_(*filters))

            result = await self.db.execute(query)
            pricing_tiers = result.scalars().all()

            return [
                await self._pricing_tier_to_response(tier)
                for tier in pricing_tiers
            ]

        except Exception as e:
            logger.error(f"Error getting vendor pricing tiers: {e}")
            raise

    async def get_pricing_tier_by_id(self, pricing_id: str) -> Optional[PricingTierResponse]:
        """Get pricing tier by ID."""
        try:
            query = select(PricingTier).where(PricingTier.id == pricing_id)
            result = await self.db.execute(query)
            pricing_tier = result.scalar_one_or_none()

            if pricing_tier:
                return await self._pricing_tier_to_response(pricing_tier)
            return None

        except Exception as e:
            logger.error(f"Error getting pricing tier by ID {pricing_id}: {e}")
            raise

    async def update_pricing_tier(self, pricing_id: str, pricing_data: PricingTierUpdate) -> PricingTierResponse:
        """Update pricing tier."""
        try:
            query = select(PricingTier).where(PricingTier.id == pricing_id)
            result = await self.db.execute(query)
            pricing_tier = result.scalar_one_or_none()

            if not pricing_tier:
                raise ValueError("Pricing tier not found")

            # Store old price for event
            old_price = float(pricing_tier.unit_price)

            # Update fields
            update_data = pricing_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(pricing_tier, field, value)

            await self.db.commit()
            await self.db.refresh(pricing_tier)

            # Publish price update event if price changed
            if "unit_price" in update_data:
                await event_service.publish_price_update(
                    str(pricing_tier.vendor_id),
                    str(pricing_tier.product_id),
                    old_price,
                    float(pricing_tier.unit_price),
                    str(pricing_tier.id)
                )

            return await self._pricing_tier_to_response(pricing_tier)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating pricing tier {pricing_id}: {e}")
            raise

    async def delete_pricing_tier(self, pricing_id: str):
        """Delete pricing tier."""
        try:
            query = select(PricingTier).where(PricingTier.id == pricing_id)
            result = await self.db.execute(query)
            pricing_tier = result.scalar_one_or_none()

            if not pricing_tier:
                raise ValueError("Pricing tier not found")

            await self.db.delete(pricing_tier)
            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting pricing tier {pricing_id}: {e}")
            raise

    async def get_vendor_by_user_id(self, user_id: str) -> Optional[Vendor]:
        """Get vendor by user ID."""
        try:
            query = select(Vendor).where(Vendor.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting vendor by user ID {user_id}: {e}")
            raise

    async def _check_vendor_serves_location(self, vendor: Vendor, latitude: float,
                                          longitude: float, max_radius: float) -> tuple[bool, Optional[float]]:
        """Check if vendor serves a specific location and return distance."""
        # Simplified implementation - in production, check against actual service areas
        if vendor.business_city and vendor.business_state:
            # Use a default distance for simplicity
            distance = 25.0  # Mock distance
            if distance <= max_radius:
                return True, distance
        return False, None

    async def _get_best_pricing_tier(self, product: ProductCatalog, quantity: int,
                                   include_emergency: bool = False) -> Optional[PricingTier]:
        """Get the best pricing tier for a product and quantity."""
        if not product.pricing_tiers:
            return None

        # Filter active tiers that match quantity requirements
        suitable_tiers = []
        for tier in product.pricing_tiers:
            if (tier.is_active and
                tier.minimum_quantity <= quantity and
                (tier.maximum_quantity is None or tier.maximum_quantity >= quantity)):
                suitable_tiers.append(tier)

        if not suitable_tiers:
            return None

        # Return tier with lowest total cost
        return min(suitable_tiers, key=lambda t: t.unit_price * quantity + t.delivery_fee)

    async def _create_vendor_pricing_option(self, product: ProductCatalog, pricing_tier: PricingTier,
                                          quantity: int, distance: float) -> VendorPricingOption:
        """Create vendor pricing option from product and pricing tier."""
        subtotal = pricing_tier.unit_price * quantity

        # Calculate discounts
        bulk_discount = subtotal * (pricing_tier.bulk_discount_percentage / 100)
        loyalty_discount = subtotal * (pricing_tier.loyalty_discount_percentage / 100)
        seasonal_discount = subtotal * (pricing_tier.seasonal_discount_percentage / 100)
        total_discount = bulk_discount + loyalty_discount + seasonal_discount

        total_price = (subtotal - total_discount +
                      pricing_tier.delivery_fee +
                      pricing_tier.setup_fee +
                      pricing_tier.handling_fee +
                      pricing_tier.emergency_surcharge)

        return VendorPricingOption(
            vendor_id=str(product.vendor_id),
            vendor_name=product.vendor.business_name,
            business_name=product.vendor.business_name,
            product_id=str(product.id),
            product_name=product.product_name,
            tier_id=str(pricing_tier.id),
            tier_name=pricing_tier.tier_name,
            unit_price=pricing_tier.unit_price,
            quantity=quantity,
            subtotal=subtotal,
            delivery_fee=pricing_tier.delivery_fee,
            setup_fee=pricing_tier.setup_fee,
            handling_fee=pricing_tier.handling_fee,
            emergency_surcharge=pricing_tier.emergency_surcharge,
            total_discount=total_discount,
            total_price=total_price,
            currency=pricing_tier.currency,
            distance_km=distance,
            estimated_delivery_hours=24,  # Mock data
            vendor_rating=product.vendor.average_rating,
            payment_terms=pricing_tier.payment_terms,
            minimum_order_value=pricing_tier.minimum_order_value,
            is_emergency_available=pricing_tier.emergency_surcharge > 0,
            certifications=[cert.get("name") for cert in (product.certifications or [])]
        )

    def _sort_pricing_options(self, options: List[VendorPricingOption], sort_by: str) -> List[VendorPricingOption]:
        """Sort pricing options based on criteria."""
        if sort_by == "price":
            return sorted(options, key=lambda x: x.total_price)
        elif sort_by == "distance":
            return sorted(options, key=lambda x: x.distance_km)
        elif sort_by == "rating":
            return sorted(options, key=lambda x: x.vendor_rating or 0, reverse=True)
        elif sort_by == "delivery_time":
            return sorted(options, key=lambda x: x.estimated_delivery_hours)
        else:
            return options

    async def _calculate_bulk_pricing_for_vendor(self, vendor: Vendor, products: List[ProductCatalog],
                                               items: List[Dict[str, Any]], distance: float) -> Optional[BulkPricingOption]:
        """Calculate bulk pricing for a vendor."""
        try:
            bulk_items = []
            subtotal = Decimal("0.0")
            total_delivery_fee = Decimal("0.0")

            for item in items:
                product_id = item.get("product_id")
                quantity = item.get("quantity", 1)

                # Find matching product
                product = next((p for p in products if str(p.id) == product_id), None)
                if not product:
                    continue

                # Get best pricing tier
                pricing_tier = await self._get_best_pricing_tier(product, quantity)
                if not pricing_tier:
                    continue

                item_subtotal = pricing_tier.unit_price * quantity
                item_total = item_subtotal + pricing_tier.delivery_fee

                bulk_item = BulkPricingItem(
                    product_id=str(product.id),
                    product_name=product.product_name,
                    quantity=quantity,
                    unit_price=pricing_tier.unit_price,
                    subtotal=item_subtotal,
                    delivery_fee=pricing_tier.delivery_fee,
                    total_price=item_total
                )

                bulk_items.append(bulk_item)
                subtotal += item_subtotal
                total_delivery_fee += pricing_tier.delivery_fee

            if not bulk_items:
                return None

            # Calculate bulk discount (simplified)
            bulk_discount = subtotal * Decimal("0.05") if subtotal > 10000 else Decimal("0.0")
            total_price = subtotal + total_delivery_fee - bulk_discount

            return BulkPricingOption(
                vendor_id=str(vendor.id),
                vendor_name=vendor.business_name,
                business_name=vendor.business_name,
                items=bulk_items,
                subtotal=subtotal,
                total_delivery_fee=total_delivery_fee,
                bulk_discount=bulk_discount,
                total_price=total_price,
                currency="NGN",
                estimated_delivery_hours=24,
                vendor_rating=vendor.average_rating,
                distance_km=distance
            )

        except Exception as e:
            logger.error(f"Error calculating bulk pricing for vendor {vendor.id}: {e}")
            return None

    def _get_recommended_bulk_option(self, options: List[BulkPricingOption]) -> Optional[BulkPricingOption]:
        """Get recommended bulk option based on multiple factors."""
        if not options:
            return None

        # Simple scoring based on price, rating, and delivery time
        def score_option(option):
            price_score = 1.0 / float(option.total_price) * 1000000  # Lower price = higher score
            rating_score = float(option.vendor_rating or 0) * 20     # Higher rating = higher score
            delivery_score = 1.0 / option.estimated_delivery_hours * 100  # Faster delivery = higher score

            return price_score + rating_score + delivery_score

        return max(options, key=score_option)

    async def _pricing_tier_to_response(self, pricing_tier: PricingTier) -> PricingTierResponse:
        """Convert pricing tier model to response schema."""
        return PricingTierResponse(
            id=str(pricing_tier.id),
            vendor_id=str(pricing_tier.vendor_id),
            product_id=str(pricing_tier.product_id),
            service_area_id=str(pricing_tier.service_area_id) if pricing_tier.service_area_id else None,
            tier_name=pricing_tier.tier_name,
            unit_price=pricing_tier.unit_price,
            currency=pricing_tier.currency,
            minimum_quantity=pricing_tier.minimum_quantity,
            maximum_quantity=pricing_tier.maximum_quantity,
            delivery_fee=pricing_tier.delivery_fee,
            setup_fee=pricing_tier.setup_fee,
            handling_fee=pricing_tier.handling_fee,
            emergency_surcharge=pricing_tier.emergency_surcharge,
            bulk_discount_percentage=pricing_tier.bulk_discount_percentage,
            loyalty_discount_percentage=pricing_tier.loyalty_discount_percentage,
            seasonal_discount_percentage=pricing_tier.seasonal_discount_percentage,
            payment_terms=pricing_tier.payment_terms,
            minimum_order_value=pricing_tier.minimum_order_value,
            cancellation_policy=pricing_tier.cancellation_policy,
            pricing_notes=pricing_tier.pricing_notes,
            effective_from=pricing_tier.effective_from,
            effective_until=pricing_tier.effective_until,
            is_active=pricing_tier.is_active,
            priority_rank=pricing_tier.priority_rank,
            is_featured=pricing_tier.is_featured,
            is_promotional=pricing_tier.is_promotional,
            internal_notes=pricing_tier.internal_notes,
            created_at=pricing_tier.created_at,
            updated_at=pricing_tier.updated_at
        )
