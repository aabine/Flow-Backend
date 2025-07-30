from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import math
import sys
import os
import logging

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.inventory import Inventory, CylinderStock
from app.schemas.inventory import (
    ProductCatalogRequest, ProductCatalogItem, ProductCatalogResponse,
    AvailabilityCheck, AvailabilityResponse, BulkAvailabilityCheck, BulkAvailabilityResponse
)
from app.core.config import get_settings
from shared.models import CylinderSize
from shared.utils import calculate_distance_km

logger = logging.getLogger(__name__)


class ProductCatalogService:
    def __init__(self):
        self.settings = get_settings()

    async def search_catalog(
        self,
        db: AsyncSession,
        request: ProductCatalogRequest,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[ProductCatalogItem], int]:
        """Search product catalog with location-based filtering and pricing."""
        try:
            # Get inventory locations within radius
            query = select(Inventory).options(
                selectinload(Inventory.stock)
            ).where(
                and_(
                    Inventory.is_active == True,
                    func.ST_DWithin(
                        func.ST_Point(Inventory.longitude, Inventory.latitude),
                        func.ST_Point(request.hospital_longitude, request.hospital_latitude),
                        request.max_distance_km * 1000  # Convert km to meters
                    )
                )
            )

            result = await db.execute(query)
            locations = result.scalars().all()

            catalog_items = []
            
            for location in locations:
                # Calculate distance
                distance_km = calculate_distance_km(
                    request.hospital_latitude, request.hospital_longitude,
                    location.latitude, location.longitude
                )

                # Get vendor info and pricing
                vendor_info = await self._get_vendor_info(location.vendor_id)
                pricing_info = await self._get_pricing_info(location.vendor_id, location.id)

                # Filter by cylinder size if specified
                stock_items = location.stock
                if request.cylinder_size:
                    stock_items = [s for s in stock_items if s.cylinder_size == request.cylinder_size]

                # Create catalog items for each cylinder size with stock
                for stock in stock_items:
                    if stock.available_quantity >= request.quantity:
                        # Get pricing for this specific cylinder size
                        cylinder_pricing = pricing_info.get(stock.cylinder_size.value, {})
                        
                        catalog_item = ProductCatalogItem(
                            vendor_id=location.vendor_id,
                            vendor_name=vendor_info.get("name", "Unknown Vendor"),
                            location_id=location.id,
                            location_name=location.location_name,
                            address=location.address,
                            city=location.city,
                            state=location.state,
                            latitude=location.latitude,
                            longitude=location.longitude,
                            distance_km=distance_km,
                            cylinder_size=stock.cylinder_size,
                            available_quantity=stock.available_quantity,
                            unit_price=cylinder_pricing.get("unit_price", 0.0),
                            delivery_fee=cylinder_pricing.get("delivery_fee", 0.0),
                            emergency_surcharge=cylinder_pricing.get("emergency_surcharge", 0.0) if request.is_emergency else 0.0,
                            minimum_order_quantity=cylinder_pricing.get("minimum_order_quantity", 1),
                            maximum_order_quantity=cylinder_pricing.get("maximum_order_quantity"),
                            estimated_delivery_time_hours=self._calculate_delivery_time(distance_km, request.is_emergency),
                            vendor_rating=vendor_info.get("rating"),
                            is_available=stock.available_quantity >= request.quantity
                        )
                        catalog_items.append(catalog_item)

            # Sort results
            catalog_items = self._sort_catalog_items(catalog_items, request.sort_by, request.sort_order)

            # Apply pagination
            total_items = len(catalog_items)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_items = catalog_items[start_index:end_index]

            return paginated_items, total_items

        except Exception as e:
            raise Exception(f"Failed to search catalog: {str(e)}")

    async def check_availability(
        self,
        db: AsyncSession,
        check: AvailabilityCheck
    ) -> Optional[AvailabilityResponse]:
        """Check real-time availability for a specific product."""
        try:
            # Get stock information
            query = select(CylinderStock).join(Inventory).where(
                and_(
                    Inventory.vendor_id == check.vendor_id,
                    Inventory.id == check.location_id,
                    CylinderStock.cylinder_size == check.cylinder_size,
                    Inventory.is_active == True
                )
            )

            result = await db.execute(query)
            stock = result.scalar_one_or_none()

            if not stock:
                return None

            # Get pricing information
            pricing_info = await self._get_pricing_info(check.vendor_id, check.location_id)
            cylinder_pricing = pricing_info.get(check.cylinder_size.value, {})

            return AvailabilityResponse(
                vendor_id=check.vendor_id,
                location_id=check.location_id,
                cylinder_size=check.cylinder_size,
                available_quantity=stock.available_quantity,
                is_available=stock.available_quantity >= check.quantity,
                unit_price=cylinder_pricing.get("unit_price"),
                delivery_fee=cylinder_pricing.get("delivery_fee"),
                estimated_delivery_time_hours=cylinder_pricing.get("estimated_delivery_time_hours"),
                last_updated=stock.updated_at or stock.created_at
            )

        except Exception as e:
            raise Exception(f"Failed to check availability: {str(e)}")

    async def bulk_check_availability(
        self,
        db: AsyncSession,
        bulk_check: BulkAvailabilityCheck
    ) -> BulkAvailabilityResponse:
        """Bulk check availability for multiple products."""
        results = []
        available_count = 0
        unavailable_count = 0

        for check in bulk_check.checks:
            try:
                availability = await self.check_availability(db, check)
                if availability:
                    results.append(availability)
                    if availability.is_available:
                        available_count += 1
                    else:
                        unavailable_count += 1
                else:
                    unavailable_count += 1
            except Exception:
                unavailable_count += 1

        return BulkAvailabilityResponse(
            results=results,
            total_checked=len(bulk_check.checks),
            available_count=available_count,
            unavailable_count=unavailable_count
        )

    async def get_vendor_products(
        self,
        db: AsyncSession,
        vendor_id: str,
        cylinder_size: Optional[CylinderSize] = None,
        location_id: Optional[str] = None
    ) -> List[ProductCatalogItem]:
        """Get all products for a specific vendor."""
        try:
            query = select(Inventory).options(
                selectinload(Inventory.stock)
            ).where(
                and_(
                    Inventory.vendor_id == vendor_id,
                    Inventory.is_active == True
                )
            )

            if location_id:
                query = query.where(Inventory.id == location_id)

            result = await db.execute(query)
            locations = result.scalars().all()

            catalog_items = []
            vendor_info = await self._get_vendor_info(vendor_id)
            pricing_info = await self._get_pricing_info(vendor_id)

            for location in locations:
                stock_items = location.stock
                if cylinder_size:
                    stock_items = [s for s in stock_items if s.cylinder_size == cylinder_size]

                for stock in stock_items:
                    if stock.available_quantity > 0:
                        cylinder_pricing = pricing_info.get(stock.cylinder_size.value, {})
                        
                        catalog_item = ProductCatalogItem(
                            vendor_id=location.vendor_id,
                            vendor_name=vendor_info.get("name", "Unknown Vendor"),
                            location_id=location.id,
                            location_name=location.location_name,
                            address=location.address,
                            city=location.city,
                            state=location.state,
                            latitude=location.latitude,
                            longitude=location.longitude,
                            distance_km=0.0,  # Not applicable for vendor-specific view
                            cylinder_size=stock.cylinder_size,
                            available_quantity=stock.available_quantity,
                            unit_price=cylinder_pricing.get("unit_price", 0.0),
                            delivery_fee=cylinder_pricing.get("delivery_fee", 0.0),
                            emergency_surcharge=cylinder_pricing.get("emergency_surcharge", 0.0),
                            minimum_order_quantity=cylinder_pricing.get("minimum_order_quantity", 1),
                            maximum_order_quantity=cylinder_pricing.get("maximum_order_quantity"),
                            estimated_delivery_time_hours=cylinder_pricing.get("estimated_delivery_time_hours", 24),
                            vendor_rating=vendor_info.get("rating"),
                            is_available=True
                        )
                        catalog_items.append(catalog_item)

            return catalog_items

        except Exception as e:
            raise Exception(f"Failed to get vendor products: {str(e)}")

    async def get_location_products(
        self,
        db: AsyncSession,
        location_id: str,
        cylinder_size: Optional[CylinderSize] = None
    ) -> List[ProductCatalogItem]:
        """Get all products for a specific location."""
        try:
            query = select(Inventory).options(
                selectinload(Inventory.stock)
            ).where(
                and_(
                    Inventory.id == location_id,
                    Inventory.is_active == True
                )
            )

            result = await db.execute(query)
            location = result.scalar_one_or_none()

            if not location:
                return []

            catalog_items = []
            vendor_info = await self._get_vendor_info(location.vendor_id)
            pricing_info = await self._get_pricing_info(location.vendor_id, location_id)

            stock_items = location.stock
            if cylinder_size:
                stock_items = [s for s in stock_items if s.cylinder_size == cylinder_size]

            for stock in stock_items:
                if stock.available_quantity > 0:
                    cylinder_pricing = pricing_info.get(stock.cylinder_size.value, {})
                    
                    catalog_item = ProductCatalogItem(
                        vendor_id=location.vendor_id,
                        vendor_name=vendor_info.get("name", "Unknown Vendor"),
                        location_id=location.id,
                        location_name=location.location_name,
                        address=location.address,
                        city=location.city,
                        state=location.state,
                        latitude=location.latitude,
                        longitude=location.longitude,
                        distance_km=0.0,
                        cylinder_size=stock.cylinder_size,
                        available_quantity=stock.available_quantity,
                        unit_price=cylinder_pricing.get("unit_price", 0.0),
                        delivery_fee=cylinder_pricing.get("delivery_fee", 0.0),
                        emergency_surcharge=cylinder_pricing.get("emergency_surcharge", 0.0),
                        minimum_order_quantity=cylinder_pricing.get("minimum_order_quantity", 1),
                        maximum_order_quantity=cylinder_pricing.get("maximum_order_quantity"),
                        estimated_delivery_time_hours=cylinder_pricing.get("estimated_delivery_time_hours", 24),
                        vendor_rating=vendor_info.get("rating"),
                        is_available=True
                    )
                    catalog_items.append(catalog_item)

            return catalog_items

        except Exception as e:
            raise Exception(f"Failed to get location products: {str(e)}")

    async def _get_vendor_info(self, vendor_id: str) -> Dict[str, Any]:
        """Get vendor information from user service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.settings.USER_SERVICE_URL}/vendors/{vendor_id}/profile"
                )
                if response.status_code == 200:
                    return response.json()
                return {"name": "Unknown Vendor", "rating": None}
        except Exception:
            return {"name": "Unknown Vendor", "rating": None}

    async def _get_pricing_info(self, vendor_id: str, location_id: str = None) -> Dict[str, Dict[str, Any]]:
        """Get pricing information from pricing service."""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.settings.PRICING_SERVICE_URL}/products"
                params = {"vendor_id": vendor_id}
                if location_id:
                    params["location_id"] = location_id
                
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    pricing_data = response.json()
                    # Convert to cylinder_size -> pricing_info mapping
                    pricing_map = {}
                    for item in pricing_data.get("items", []):
                        pricing_map[item["cylinder_size"]] = {
                            "unit_price": float(item["unit_price"]),
                            "delivery_fee": float(item["delivery_fee"]),
                            "emergency_surcharge": float(item["emergency_surcharge"]),
                            "minimum_order_quantity": item["minimum_order_quantity"],
                            "maximum_order_quantity": item["maximum_order_quantity"],
                            "estimated_delivery_time_hours": 24  # Default
                        }
                    return pricing_map
                return {}
        except Exception:
            return {}

    def _calculate_delivery_time(self, distance_km: float, is_emergency: bool = False) -> int:
        """Calculate estimated delivery time based on distance."""
        if is_emergency:
            # Emergency deliveries: 1-3 hours depending on distance
            return max(1, min(3, int(distance_km / 20) + 1))
        else:
            # Regular deliveries: 4-24 hours depending on distance
            return max(4, min(24, int(distance_km / 10) + 4))

    def _sort_catalog_items(
        self,
        items: List[ProductCatalogItem],
        sort_by: str,
        sort_order: str
    ) -> List[ProductCatalogItem]:
        """Sort catalog items by specified criteria."""
        reverse = sort_order == "desc"
        
        if sort_by == "distance":
            return sorted(items, key=lambda x: x.distance_km, reverse=reverse)
        elif sort_by == "price":
            return sorted(items, key=lambda x: x.unit_price, reverse=reverse)
        elif sort_by == "rating":
            return sorted(items, key=lambda x: x.vendor_rating or 0, reverse=reverse)
        elif sort_by == "delivery_time":
            return sorted(items, key=lambda x: x.estimated_delivery_time_hours, reverse=reverse)
        else:
            return items

    async def get_featured_products(
        self,
        db: AsyncSession,
        limit: int = 10
    ) -> List[ProductCatalogItem]:
        """Get featured products for public display."""
        try:
            # Query for featured products (high availability, good ratings)
            query = select(Inventory).where(
                and_(
                    Inventory.quantity > 0,
                    Inventory.is_available == True
                )
            ).order_by(
                desc(Inventory.quantity),  # Prioritize high stock
                desc(Inventory.updated_at)  # Recent updates
            ).limit(limit)

            result = await db.execute(query)
            inventory_items = result.scalars().all()

            catalog_items = []
            for item in inventory_items:
                # Get vendor info
                vendor_info = await self._get_vendor_info(str(item.vendor_id))

                # Get pricing info
                pricing_info = await self._get_pricing_info(str(item.vendor_id), str(item.location_id))

                catalog_item = ProductCatalogItem(
                    id=str(item.id),
                    vendor_id=str(item.vendor_id),
                    vendor_name=vendor_info.get("name", "Unknown Vendor"),
                    vendor_rating=vendor_info.get("rating", 0.0),
                    location_id=str(item.location_id),
                    location_name=vendor_info.get("location_name", "Unknown Location"),
                    product_type=item.product_type,
                    cylinder_size=item.cylinder_size,
                    quantity_available=item.quantity,
                    unit_price=pricing_info.get(item.product_type, {}).get("unit_price", 0.0),
                    bulk_price=pricing_info.get(item.product_type, {}).get("bulk_price", 0.0),
                    minimum_order=pricing_info.get(item.product_type, {}).get("minimum_order", 1),
                    delivery_time_hours=24,  # Default delivery time
                    distance_km=0.0,  # No distance for featured products
                    is_emergency_available=item.emergency_stock > 0,
                    last_updated=item.updated_at
                )
                catalog_items.append(catalog_item)

            return catalog_items

        except Exception as e:
            logger.error(f"Error getting featured products: {e}")
            return []

    async def get_nearby_products(
        self,
        db: AsyncSession,
        latitude: float,
        longitude: float,
        cylinder_size: str = None,
        quantity: int = 1,
        max_distance_km: float = 50.0,
        is_emergency: bool = False,
        sort_by: str = "distance",
        page: int = 1,
        page_size: int = 20,
        user_context: dict = None
    ) -> ProductCatalogResponse:
        """Get nearby products for public search."""
        try:
            # Build query for nearby products
            query = select(Inventory).where(
                and_(
                    Inventory.quantity >= quantity,
                    Inventory.is_available == True
                )
            )

            if cylinder_size:
                query = query.where(Inventory.cylinder_size == cylinder_size)

            if is_emergency:
                query = query.where(Inventory.emergency_stock >= quantity)

            result = await db.execute(query)
            inventory_items = result.scalars().all()

            catalog_items = []
            for item in inventory_items:
                # Calculate distance (simplified - in real implementation, use proper geospatial queries)
                distance_km = 10.0  # Placeholder distance calculation

                if distance_km <= max_distance_km:
                    # Get vendor info
                    vendor_info = await self._get_vendor_info(str(item.vendor_id))

                    # Get pricing info
                    pricing_info = await self._get_pricing_info(str(item.vendor_id), str(item.location_id))

                    catalog_item = ProductCatalogItem(
                        id=str(item.id),
                        vendor_id=str(item.vendor_id),
                        vendor_name=vendor_info.get("name", "Unknown Vendor"),
                        vendor_rating=vendor_info.get("rating", 0.0),
                        location_id=str(item.location_id),
                        location_name=vendor_info.get("location_name", "Unknown Location"),
                        product_type=item.product_type,
                        cylinder_size=item.cylinder_size,
                        quantity_available=item.quantity,
                        unit_price=pricing_info.get(item.product_type, {}).get("unit_price", 0.0),
                        bulk_price=pricing_info.get(item.product_type, {}).get("bulk_price", 0.0),
                        minimum_order=pricing_info.get(item.product_type, {}).get("minimum_order", 1),
                        delivery_time_hours=self._calculate_delivery_time(distance_km, is_emergency),
                        distance_km=distance_km,
                        is_emergency_available=item.emergency_stock > 0,
                        last_updated=item.updated_at
                    )
                    catalog_items.append(catalog_item)

            # Sort results
            sorted_items = self._sort_catalog_items(catalog_items, sort_by, latitude, longitude)

            # Paginate
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_items = sorted_items[start_idx:end_idx]

            return ProductCatalogResponse(
                items=paginated_items,
                total_count=len(catalog_items),
                page=page,
                page_size=page_size,
                total_pages=(len(catalog_items) + page_size - 1) // page_size
            )

        except Exception as e:
            logger.error(f"Error getting nearby products: {e}")
            return ProductCatalogResponse(
                items=[],
                total_count=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )
