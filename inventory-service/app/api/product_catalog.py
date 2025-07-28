from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.inventory_service import InventoryService
from app.services.product_catalog_service import ProductCatalogService
from app.schemas.inventory import (
    ProductCatalogRequest, ProductCatalogResponse, ProductCatalogItem,
    AvailabilityCheck, AvailabilityResponse, BulkAvailabilityCheck, BulkAvailabilityResponse
)
from shared.models import APIResponse, UserRole, CylinderSize
from shared.auth import get_current_user

router = APIRouter()
inventory_service = InventoryService()
catalog_service = ProductCatalogService()


@router.post("/search", response_model=ProductCatalogResponse)
async def search_product_catalog(
    catalog_request: ProductCatalogRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search product catalog with location-based filtering."""
    try:
        # Only hospitals can search the catalog
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can search the product catalog")

        catalog_items = await catalog_service.search_catalog(
            db=db,
            request=catalog_request
        )

        return ProductCatalogResponse(
            items=catalog_items,
            total=len(catalog_items),
            search_radius_km=catalog_request.max_distance_km,
            hospital_location={
                "latitude": catalog_request.hospital_latitude,
                "longitude": catalog_request.hospital_longitude
            },
            filters_applied=catalog_request
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search product catalog: {str(e)}"
        )


@router.get("/nearby", response_model=ProductCatalogResponse)
async def get_nearby_products(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    cylinder_size: Optional[str] = Query(None),
    quantity: int = Query(1, gt=0),
    max_distance_km: float = Query(50.0, gt=0),
    is_emergency: bool = Query(False),
    sort_by: str = Query("distance", regex="^(distance|price|rating|delivery_time)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get nearby products based on hospital location."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can access product catalog")

        catalog_request = ProductCatalogRequest(
            hospital_latitude=latitude,
            hospital_longitude=longitude,
            cylinder_size=CylinderSize(cylinder_size) if cylinder_size else None,
            quantity=quantity,
            max_distance_km=max_distance_km,
            is_emergency=is_emergency,
            sort_by=sort_by
        )

        catalog_items = await catalog_service.search_catalog(
            db=db,
            request=catalog_request
        )

        return ProductCatalogResponse(
            items=catalog_items,
            total=len(catalog_items),
            search_radius_km=max_distance_km,
            hospital_location={"latitude": latitude, "longitude": longitude},
            filters_applied=catalog_request
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get nearby products: {str(e)}"
        )


@router.post("/availability/check", response_model=AvailabilityResponse)
async def check_availability(
    availability_check: AvailabilityCheck,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check real-time availability for a specific product."""
    try:
        if current_user["role"] not in [UserRole.HOSPITAL, UserRole.VENDOR]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        availability = await catalog_service.check_availability(
            db=db,
            check=availability_check
        )

        if not availability:
            raise HTTPException(status_code=404, detail="Product not found or unavailable")

        return availability
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check availability: {str(e)}"
        )


@router.post("/availability/bulk-check", response_model=BulkAvailabilityResponse)
async def bulk_check_availability(
    bulk_check: BulkAvailabilityCheck,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Bulk check availability for multiple products."""
    try:
        if current_user["role"] not in [UserRole.HOSPITAL, UserRole.VENDOR]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        results = await catalog_service.bulk_check_availability(
            db=db,
            bulk_check=bulk_check
        )

        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk check availability: {str(e)}"
        )


@router.get("/vendor/{vendor_id}/products", response_model=List[ProductCatalogItem])
async def get_vendor_products(
    vendor_id: str,
    cylinder_size: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all products for a specific vendor."""
    try:
        products = await catalog_service.get_vendor_products(
            db=db,
            vendor_id=vendor_id,
            cylinder_size=CylinderSize(cylinder_size) if cylinder_size else None,
            location_id=location_id
        )

        return products
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor products: {str(e)}"
        )


@router.get("/location/{location_id}/products", response_model=List[ProductCatalogItem])
async def get_location_products(
    location_id: str,
    cylinder_size: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all products for a specific location."""
    try:
        products = await catalog_service.get_location_products(
            db=db,
            location_id=location_id,
            cylinder_size=CylinderSize(cylinder_size) if cylinder_size else None
        )

        return products
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get location products: {str(e)}"
        )


@router.get("/featured", response_model=List[ProductCatalogItem])
async def get_featured_products(
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get featured products (top-rated vendors with good availability)."""
    try:
        products = await catalog_service.get_featured_products(
            db=db,
            limit=limit
        )

        return products
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get featured products: {str(e)}"
        )


@router.get("/emergency", response_model=List[ProductCatalogItem])
async def get_emergency_products(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    cylinder_size: Optional[str] = Query(None),
    max_distance_km: float = Query(25.0, gt=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get emergency products (fastest delivery, closest vendors)."""
    try:
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(status_code=403, detail="Only hospitals can access emergency products")

        products = await catalog_service.get_emergency_products(
            db=db,
            latitude=latitude,
            longitude=longitude,
            cylinder_size=CylinderSize(cylinder_size) if cylinder_size else None,
            max_distance_km=max_distance_km
        )

        return products
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emergency products: {str(e)}"
        )
