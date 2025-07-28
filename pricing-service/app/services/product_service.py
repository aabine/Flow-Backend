from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging
import math

from app.models.vendor import Vendor
from app.models.product import ProductCatalog, ProductAvailability
from app.models.pricing import PricingTier
from app.schemas.product import (
    ProductCreate, ProductUpdate, ProductResponse, ProductListResponse,
    ProductSearchRequest, ProductCatalogResponse, ProductCatalogItem,
    ProductAvailabilityRequest, ProductAvailabilityResponse, ProductAvailabilityItem
)
from app.services.event_service import event_service

logger = logging.getLogger(__name__)


class ProductService:
    """Service for product management operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_product_catalog(self, search_request: ProductSearchRequest) -> ProductCatalogResponse:
        """Get product catalog with location-based filtering."""
        try:
            # Build base query with joins
            query = select(ProductCatalog).options(
                joinedload(ProductCatalog.vendor),
                joinedload(ProductCatalog.pricing_tiers)
            )
            
            # Apply basic filters
            filters = [
                ProductCatalog.is_active == True,
                ProductCatalog.approval_status == "approved"
            ]
            
            if search_request.product_category:
                filters.append(ProductCatalog.product_category == search_request.product_category)
            
            if search_request.cylinder_size:
                filters.append(ProductCatalog.cylinder_size == search_request.cylinder_size)
            
            if search_request.vendor_id:
                filters.append(ProductCatalog.vendor_id == search_request.vendor_id)
            
            if search_request.min_price:
                filters.append(ProductCatalog.base_price >= search_request.min_price)
            
            if search_request.max_price:
                filters.append(ProductCatalog.base_price <= search_request.max_price)
            
            if search_request.in_stock_only:
                filters.append(ProductCatalog.stock_status == "in_stock")
            
            if search_request.featured_only:
                filters.append(ProductCatalog.is_featured == True)
            
            query = query.where(and_(*filters))
            
            # Execute query
            result = await self.db.execute(query)
            products = result.scalars().all()
            
            # Filter by location if coordinates provided
            catalog_items = []
            if search_request.latitude and search_request.longitude:
                for product in products:
                    # Check if vendor serves the location
                    vendor = product.vendor
                    serves_location, distance = await self._check_vendor_serves_location(
                        vendor, search_request.latitude, search_request.longitude, 
                        search_request.radius_km or 50.0
                    )
                    
                    if serves_location:
                        catalog_item = await self._product_to_catalog_item(product, distance)
                        catalog_items.append(catalog_item)
            else:
                # No location filtering
                for product in products:
                    catalog_item = await self._product_to_catalog_item(product)
                    catalog_items.append(catalog_item)
            
            # Apply sorting
            catalog_items = self._sort_catalog_items(catalog_items, search_request.sort_by)
            
            # Apply pagination
            total = len(catalog_items)
            start_idx = (search_request.page - 1) * search_request.page_size
            end_idx = start_idx + search_request.page_size
            paginated_items = catalog_items[start_idx:end_idx]
            
            total_pages = math.ceil(total / search_request.page_size)
            
            return ProductCatalogResponse(
                items=paginated_items,
                total=total,
                page=search_request.page,
                page_size=search_request.page_size,
                total_pages=total_pages,
                search_criteria=search_request,
                filters_applied={
                    "category": search_request.product_category,
                    "cylinder_size": search_request.cylinder_size,
                    "price_range": {
                        "min": search_request.min_price,
                        "max": search_request.max_price
                    },
                    "location": {
                        "latitude": search_request.latitude,
                        "longitude": search_request.longitude,
                        "radius_km": search_request.radius_km
                    } if search_request.latitude and search_request.longitude else None
                }
            )
            
        except Exception as e:
            logger.error(f"Error getting product catalog: {e}")
            raise
    
    async def search_products(self, search_request: ProductSearchRequest) -> ProductCatalogResponse:
        """Advanced product search with text search."""
        try:
            # Build base query
            query = select(ProductCatalog).options(
                joinedload(ProductCatalog.vendor),
                joinedload(ProductCatalog.pricing_tiers)
            )
            
            # Apply filters
            filters = [
                ProductCatalog.is_active == True,
                ProductCatalog.approval_status == "approved"
            ]
            
            # Text search
            if search_request.query:
                search_term = f"%{search_request.query}%"
                text_filters = [
                    ProductCatalog.product_name.ilike(search_term),
                    ProductCatalog.description.ilike(search_term),
                    ProductCatalog.product_code.ilike(search_term),
                    ProductCatalog.brand.ilike(search_term),
                    ProductCatalog.manufacturer.ilike(search_term)
                ]
                filters.append(or_(*text_filters))
            
            # Apply other filters (same as get_product_catalog)
            if search_request.product_category:
                filters.append(ProductCatalog.product_category == search_request.product_category)
            
            if search_request.cylinder_size:
                filters.append(ProductCatalog.cylinder_size == search_request.cylinder_size)
            
            if search_request.vendor_id:
                filters.append(ProductCatalog.vendor_id == search_request.vendor_id)
            
            if search_request.min_price:
                filters.append(ProductCatalog.base_price >= search_request.min_price)
            
            if search_request.max_price:
                filters.append(ProductCatalog.base_price <= search_request.max_price)
            
            if search_request.in_stock_only:
                filters.append(ProductCatalog.stock_status == "in_stock")
            
            if search_request.featured_only:
                filters.append(ProductCatalog.is_featured == True)
            
            query = query.where(and_(*filters))
            
            # Execute and process results (same as get_product_catalog)
            result = await self.db.execute(query)
            products = result.scalars().all()
            
            # Process results similar to get_product_catalog
            catalog_items = []
            if search_request.latitude and search_request.longitude:
                for product in products:
                    vendor = product.vendor
                    serves_location, distance = await self._check_vendor_serves_location(
                        vendor, search_request.latitude, search_request.longitude, 
                        search_request.radius_km or 50.0
                    )
                    
                    if serves_location:
                        catalog_item = await self._product_to_catalog_item(product, distance)
                        catalog_items.append(catalog_item)
            else:
                for product in products:
                    catalog_item = await self._product_to_catalog_item(product)
                    catalog_items.append(catalog_item)
            
            # Apply sorting and pagination
            catalog_items = self._sort_catalog_items(catalog_items, search_request.sort_by)
            
            total = len(catalog_items)
            start_idx = (search_request.page - 1) * search_request.page_size
            end_idx = start_idx + search_request.page_size
            paginated_items = catalog_items[start_idx:end_idx]
            
            total_pages = math.ceil(total / search_request.page_size)
            
            return ProductCatalogResponse(
                items=paginated_items,
                total=total,
                page=search_request.page,
                page_size=search_request.page_size,
                total_pages=total_pages,
                search_criteria=search_request,
                filters_applied={
                    "query": search_request.query,
                    "category": search_request.product_category,
                    "cylinder_size": search_request.cylinder_size,
                    "price_range": {
                        "min": search_request.min_price,
                        "max": search_request.max_price
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            raise

    async def check_product_availability(self, availability_request: ProductAvailabilityRequest) -> ProductAvailabilityResponse:
        """Check real-time availability for specific products."""
        try:
            availability_items = []

            for product_id in availability_request.product_ids:
                # Get product with vendor and pricing info
                query = select(ProductCatalog).options(
                    joinedload(ProductCatalog.vendor),
                    joinedload(ProductCatalog.pricing_tiers)
                ).where(ProductCatalog.id == product_id)

                result = await self.db.execute(query)
                product = result.scalar_one_or_none()

                if not product:
                    continue

                # Check if vendor serves the location (if coordinates provided)
                if availability_request.latitude and availability_request.longitude:
                    serves_location, distance = await self._check_vendor_serves_location(
                        product.vendor, availability_request.latitude, availability_request.longitude,
                        availability_request.radius_km or 50.0
                    )

                    if not serves_location:
                        continue

                # Get availability data (simplified - in production, integrate with inventory service)
                available_quantity = 100  # Mock data
                reserved_quantity = 10    # Mock data

                # Get pricing
                pricing_tier = None
                if product.pricing_tiers:
                    # Find appropriate pricing tier for the quantity
                    for tier in product.pricing_tiers:
                        if (tier.is_active and
                            tier.minimum_quantity <= availability_request.quantity and
                            (tier.maximum_quantity is None or tier.maximum_quantity >= availability_request.quantity)):
                            pricing_tier = tier
                            break

                if pricing_tier:
                    unit_price = pricing_tier.unit_price
                    delivery_fee = pricing_tier.delivery_fee
                    total_price = (unit_price * availability_request.quantity) + delivery_fee
                else:
                    unit_price = product.base_price or Decimal("0.0")
                    delivery_fee = Decimal("0.0")
                    total_price = unit_price * availability_request.quantity

                availability_item = ProductAvailabilityItem(
                    product_id=str(product.id),
                    vendor_id=str(product.vendor_id),
                    vendor_name=product.vendor.business_name,
                    available_quantity=available_quantity,
                    reserved_quantity=reserved_quantity,
                    is_available=available_quantity >= availability_request.quantity,
                    estimated_delivery_hours=24,  # Mock data
                    unit_price=unit_price,
                    delivery_fee=delivery_fee,
                    total_price=total_price
                )

                availability_items.append(availability_item)

            return ProductAvailabilityResponse(
                items=availability_items,
                requested_quantity=availability_request.quantity,
                total_available_vendors=len(availability_items),
                search_radius_km=availability_request.radius_km or 50.0
            )

        except Exception as e:
            logger.error(f"Error checking product availability: {e}")
            raise

    async def get_vendor_products(self, vendor_id: str, page: int = 1, page_size: int = 20,
                                category: Optional[str] = None, in_stock_only: bool = True) -> ProductListResponse:
        """Get all products from a specific vendor."""
        try:
            # Build query
            query = select(ProductCatalog).where(ProductCatalog.vendor_id == vendor_id)

            # Apply filters
            filters = [ProductCatalog.is_active == True]

            if category:
                filters.append(ProductCatalog.product_category == category)

            if in_stock_only:
                filters.append(ProductCatalog.stock_status == "in_stock")

            query = query.where(and_(*filters))

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            # Apply pagination
            query = query.offset((page - 1) * page_size).limit(page_size)

            # Execute query
            result = await self.db.execute(query)
            products = result.scalars().all()

            # Convert to response format
            product_responses = []
            for product in products:
                product_response = await self._product_to_response(product)
                product_responses.append(product_response)

            total_pages = math.ceil(total / page_size)

            return ProductListResponse(
                products=product_responses,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )

        except Exception as e:
            logger.error(f"Error getting vendor products: {e}")
            raise

    async def get_product_by_id(self, product_id: str) -> Optional[ProductResponse]:
        """Get product by ID."""
        try:
            query = select(ProductCatalog).options(
                joinedload(ProductCatalog.vendor),
                joinedload(ProductCatalog.pricing_tiers)
            ).where(ProductCatalog.id == product_id)

            result = await self.db.execute(query)
            product = result.scalar_one_or_none()

            if product:
                return await self._product_to_response(product)
            return None

        except Exception as e:
            logger.error(f"Error getting product by ID {product_id}: {e}")
            raise

    async def create_product(self, product_data: ProductCreate, vendor_user_id: str) -> ProductResponse:
        """Create a new product for a vendor."""
        try:
            # Get vendor by user ID
            vendor_query = select(Vendor).where(Vendor.user_id == vendor_user_id)
            vendor_result = await self.db.execute(vendor_query)
            vendor = vendor_result.scalar_one_or_none()

            if not vendor:
                raise ValueError("Vendor not found for user")

            # Create product
            product = ProductCatalog(
                vendor_id=vendor.id,
                product_code=product_data.product_code,
                product_name=product_data.product_name,
                product_category=product_data.product_category,
                product_subcategory=product_data.product_subcategory,
                cylinder_size=product_data.cylinder_size,
                capacity_liters=product_data.capacity_liters,
                pressure_bar=product_data.pressure_bar,
                gas_type=product_data.gas_type,
                purity_percentage=product_data.purity_percentage,
                weight_kg=product_data.weight_kg,
                material=product_data.material,
                color=product_data.color,
                description=product_data.description,
                usage_instructions=product_data.usage_instructions,
                safety_information=product_data.safety_information,
                minimum_order_quantity=product_data.minimum_order_quantity,
                maximum_order_quantity=product_data.maximum_order_quantity,
                base_price=product_data.base_price,
                currency=product_data.currency,
                vendor_product_code=product_data.vendor_product_code,
                manufacturer=product_data.manufacturer,
                brand=product_data.brand,
                model_number=product_data.model_number,
                requires_special_handling=product_data.requires_special_handling,
                hazardous_material=product_data.hazardous_material,
                storage_requirements=product_data.storage_requirements,
                shelf_life_days=product_data.shelf_life_days
            )

            self.db.add(product)
            await self.db.commit()
            await self.db.refresh(product)

            # Publish product added event
            await event_service.publish_product_added(
                str(vendor.id),
                str(product.id),
                {
                    "product_name": product.product_name,
                    "product_category": product.product_category,
                    "cylinder_size": product.cylinder_size,
                    "base_price": product.base_price
                }
            )

            return await self._product_to_response(product)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating product: {e}")
            raise

    async def update_product(self, product_id: str, product_data: ProductUpdate) -> ProductResponse:
        """Update product information."""
        try:
            query = select(ProductCatalog).where(ProductCatalog.id == product_id)
            result = await self.db.execute(query)
            product = result.scalar_one_or_none()

            if not product:
                raise ValueError("Product not found")

            # Update fields
            update_data = product_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(product, field, value)

            await self.db.commit()
            await self.db.refresh(product)

            return await self._product_to_response(product)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating product {product_id}: {e}")
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
        # This is a simplified implementation
        # In production, you'd check against the vendor's service areas
        min_distance = float('inf')
        serves_location = False

        # For now, assume all vendors serve within 50km of their business location
        # In production, check against actual service areas
        if vendor.business_city and vendor.business_state:
            # Use a default distance for simplicity
            distance = 25.0  # Mock distance
            if distance <= max_radius:
                serves_location = True
                min_distance = distance

        return serves_location, min_distance if serves_location else None

    async def _product_to_catalog_item(self, product: ProductCatalog, distance: Optional[float] = None) -> ProductCatalogItem:
        """Convert product to catalog item with vendor and pricing info."""
        # Get best pricing tier
        best_price = product.base_price or Decimal("0.0")
        delivery_fee = Decimal("0.0")
        emergency_surcharge = Decimal("0.0")

        if product.pricing_tiers:
            active_tiers = [tier for tier in product.pricing_tiers if tier.is_active]
            if active_tiers:
                # Get the tier with lowest unit price
                best_tier = min(active_tiers, key=lambda t: t.unit_price)
                best_price = best_tier.unit_price
                delivery_fee = best_tier.delivery_fee
                emergency_surcharge = best_tier.emergency_surcharge

        return ProductCatalogItem(
            product_id=str(product.id),
            vendor_id=str(product.vendor_id),
            vendor_name=product.vendor.business_name,
            business_name=product.vendor.business_name,
            product_name=product.product_name,
            product_category=product.product_category,
            cylinder_size=product.cylinder_size,
            capacity_liters=product.capacity_liters,
            description=product.description,
            base_price=best_price,
            currency=product.currency,
            minimum_order_quantity=product.minimum_order_quantity,
            maximum_order_quantity=product.maximum_order_quantity,
            is_available=product.is_available,
            stock_status=product.stock_status,
            vendor_rating=product.vendor.average_rating,
            distance_km=distance,
            estimated_delivery_hours=24,  # Mock data
            delivery_fee=delivery_fee,
            emergency_surcharge=emergency_surcharge,
            product_images=product.product_images,
            certifications=[cert.get("name") for cert in (product.certifications or [])],
            features=product.features
        )

    async def _product_to_response(self, product: ProductCatalog) -> ProductResponse:
        """Convert product model to response schema."""
        return ProductResponse(
            id=str(product.id),
            vendor_id=str(product.vendor_id),
            product_code=product.product_code,
            product_name=product.product_name,
            product_category=product.product_category,
            product_subcategory=product.product_subcategory,
            cylinder_size=product.cylinder_size,
            capacity_liters=product.capacity_liters,
            pressure_bar=product.pressure_bar,
            gas_type=product.gas_type,
            purity_percentage=product.purity_percentage,
            weight_kg=product.weight_kg,
            material=product.material,
            color=product.color,
            description=product.description,
            usage_instructions=product.usage_instructions,
            safety_information=product.safety_information,
            minimum_order_quantity=product.minimum_order_quantity,
            maximum_order_quantity=product.maximum_order_quantity,
            base_price=product.base_price,
            currency=product.currency,
            vendor_product_code=product.vendor_product_code,
            manufacturer=product.manufacturer,
            brand=product.brand,
            model_number=product.model_number,
            requires_special_handling=product.requires_special_handling,
            hazardous_material=product.hazardous_material,
            storage_requirements=product.storage_requirements,
            shelf_life_days=product.shelf_life_days,
            dimensions=product.dimensions,
            features=product.features,
            specifications=product.specifications,
            certifications=product.certifications,
            regulatory_approvals=product.regulatory_approvals,
            quality_standards=product.quality_standards,
            product_images=product.product_images,
            product_documents=product.product_documents,
            is_available=product.is_available,
            stock_status=product.stock_status,
            is_featured=product.is_featured,
            is_active=product.is_active,
            approval_status=product.approval_status,
            search_keywords=product.search_keywords,
            tags=product.tags,
            created_at=product.created_at,
            updated_at=product.updated_at,
            approved_at=product.approved_at
        )

    def _sort_catalog_items(self, items: List[ProductCatalogItem], sort_by: str) -> List[ProductCatalogItem]:
        """Sort catalog items based on sort criteria."""
        if sort_by == "price_asc":
            return sorted(items, key=lambda x: x.base_price)
        elif sort_by == "price_desc":
            return sorted(items, key=lambda x: x.base_price, reverse=True)
        elif sort_by == "rating":
            return sorted(items, key=lambda x: x.vendor_rating or 0, reverse=True)
        elif sort_by == "distance":
            return sorted(items, key=lambda x: x.distance_km or float('inf'))
        elif sort_by == "newest":
            return items  # Already sorted by creation date in query
        else:  # relevance (default)
            return items
