from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.core.database import get_db
from app.schemas.product import (
    ProductResponse, ProductListResponse, ProductSearchRequest,
    ProductCatalogResponse, ProductAvailabilityRequest, ProductAvailabilityResponse,
    ProductCreate, ProductUpdate
)
from app.services.product_service import ProductService
from shared.security.auth import get_current_user
from shared.models import UserRole

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/catalog", response_model=ProductCatalogResponse)
async def get_product_catalog(
    latitude: float = Query(..., ge=-90, le=90, description="Hospital latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Hospital longitude"),
    radius_km: float = Query(50.0, gt=0, le=200, description="Search radius in kilometers"),
    product_category: Optional[str] = Query(None, description="Filter by product category"),
    cylinder_size: Optional[str] = Query(None, description="Filter by cylinder size"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    in_stock_only: bool = Query(True, description="Show only in-stock products"),
    featured_only: bool = Query(False, description="Show only featured products"),
    sort_by: str = Query("relevance", description="Sort by: relevance, price_asc, price_desc, rating, distance, newest"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Browse product catalog with location-based filtering.
    
    Returns products from vendors within the specified radius,
    with pricing, availability, and vendor information.
    """
    try:
        # Only hospitals can browse the product catalog
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can browse the product catalog"
            )

        search_request = ProductSearchRequest(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            product_category=product_category,
            cylinder_size=cylinder_size,
            min_price=min_price,
            max_price=max_price,
            in_stock_only=in_stock_only,
            featured_only=featured_only,
            sort_by=sort_by,
            page=page,
            page_size=page_size
        )

        product_service = ProductService(db)
        catalog = await product_service.get_product_catalog(search_request)
        
        logger.info(f"Retrieved {len(catalog.items)} products for hospital {current_user['user_id']}")
        return catalog

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product catalog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product catalog"
        )


@router.post("/search", response_model=ProductCatalogResponse)
async def search_products(
    search_request: ProductSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Advanced product search with multiple filters.
    
    Provides comprehensive search functionality with text search,
    category filters, price ranges, and geographical constraints.
    """
    try:
        # Only hospitals can search products
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can search products"
            )

        product_service = ProductService(db)
        results = await product_service.search_products(search_request)
        
        logger.info(f"Product search returned {len(results.items)} results for hospital {current_user['user_id']}")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search products"
        )


@router.post("/availability/check", response_model=ProductAvailabilityResponse)
async def check_product_availability(
    availability_request: ProductAvailabilityRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Check real-time availability for specific products.
    
    Returns current stock levels, pricing, and delivery estimates
    for the requested products from available vendors.
    """
    try:
        # Only hospitals can check availability
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can check product availability"
            )

        product_service = ProductService(db)
        availability = await product_service.check_product_availability(availability_request)
        
        logger.info(f"Checked availability for {len(availability_request.product_ids)} products")
        return availability

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking product availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check product availability"
        )


@router.get("/vendors/{vendor_id}/products", response_model=ProductListResponse)
async def get_vendor_products(
    vendor_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    in_stock_only: bool = Query(True, description="Show only in-stock products"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all products from a specific vendor.
    
    Returns the complete product catalog for a vendor with
    filtering options for category and stock status.
    """
    try:
        product_service = ProductService(db)
        products = await product_service.get_vendor_products(
            vendor_id=vendor_id,
            page=page,
            page_size=page_size,
            category=category,
            in_stock_only=in_stock_only
        )
        
        logger.info(f"Retrieved {len(products.products)} products for vendor {vendor_id}")
        return products

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving vendor products: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vendor products"
        )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product_details(
    product_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific product.
    
    Returns comprehensive product information including specifications,
    certifications, images, and current availability.
    """
    try:
        product_service = ProductService(db)
        product = await product_service.get_product_by_id(product_id)
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        logger.info(f"Retrieved product details for {product_id}")
        return product

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product details"
        )


# Vendor-specific endpoints for managing their products
@router.post("/", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new product in vendor's catalog.
    
    Allows vendors to add new products to their catalog
    with detailed specifications and pricing information.
    """
    try:
        # Only vendors can create products
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create products"
            )

        product_service = ProductService(db)
        product = await product_service.create_product(
            product_data=product_data,
            vendor_user_id=current_user["user_id"]
        )
        
        logger.info(f"Created product {product.id} for vendor {current_user['user_id']}")
        return product

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update product information.
    
    Allows vendors to update their product details,
    pricing, and availability status.
    """
    try:
        product_service = ProductService(db)
        
        # Get existing product
        product = await product_service.get_product_by_id(product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Check permissions
        if current_user["role"] == UserRole.VENDOR:
            # Vendors can only update their own products
            vendor = await product_service.get_vendor_by_user_id(current_user["user_id"])
            if not vendor or product.vendor_id != vendor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update your own products"
                )
        elif current_user["role"] not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to update product"
            )

        updated_product = await product_service.update_product(product_id, product_data)
        
        logger.info(f"Updated product {product_id} by user {current_user['user_id']}")
        return updated_product

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating product {product_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product"
        )
