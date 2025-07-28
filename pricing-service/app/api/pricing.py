from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.core.database import get_db
from app.schemas.pricing import (
    PriceComparisonRequest, PriceComparisonResponse,
    BulkPricingRequest, BulkPricingResponse,
    PricingTierCreate, PricingTierUpdate, PricingTierResponse,
    PriceAlertCreate, PriceAlertResponse,
    MarketPricingResponse
)
from app.services.pricing_service import PricingService
from shared.security.auth import get_current_user
from shared.models import UserRole

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/compare", response_model=PriceComparisonResponse)
async def compare_prices(
    comparison_request: PriceComparisonRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compare prices across multiple vendors for specific products.
    
    Returns pricing options from different vendors with recommendations
    for best price, fastest delivery, and highest-rated vendors.
    """
    try:
        # Only hospitals can compare prices
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can compare prices"
            )

        pricing_service = PricingService(db)
        comparison = await pricing_service.compare_prices(comparison_request)
        
        logger.info(f"Price comparison returned {len(comparison.options)} options for hospital {current_user['user_id']}")
        return comparison

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing prices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compare prices"
        )


@router.post("/bulk", response_model=BulkPricingResponse)
async def get_bulk_pricing(
    bulk_request: BulkPricingRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get bulk pricing for multiple products from vendors.
    
    Returns optimized pricing for bulk orders with potential
    discounts and consolidated delivery options.
    """
    try:
        # Only hospitals can request bulk pricing
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can request bulk pricing"
            )

        pricing_service = PricingService(db)
        bulk_pricing = await pricing_service.get_bulk_pricing(bulk_request)
        
        logger.info(f"Bulk pricing returned {len(bulk_pricing.options)} options for {len(bulk_request.items)} items")
        return bulk_pricing

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bulk pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get bulk pricing"
        )


@router.get("/products/{product_id}/vendors", response_model=PriceComparisonResponse)
async def get_product_vendor_pricing(
    product_id: str,
    quantity: int = Query(1, ge=1, description="Quantity needed"),
    latitude: float = Query(..., ge=-90, le=90, description="Hospital latitude"),
    longitude: float = Query(..., ge=-180, le=180, description="Hospital longitude"),
    radius_km: float = Query(50.0, gt=0, le=200, description="Search radius in kilometers"),
    include_emergency: bool = Query(False, description="Include emergency pricing"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get pricing from all vendors for a specific product.
    
    Returns comprehensive pricing comparison for a single product
    across all available vendors in the specified area.
    """
    try:
        # Only hospitals can get vendor pricing
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can view vendor pricing"
            )

        comparison_request = PriceComparisonRequest(
            product_id=product_id,
            quantity=quantity,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            include_emergency_pricing=include_emergency
        )

        pricing_service = PricingService(db)
        pricing_options = await pricing_service.compare_prices(comparison_request)
        
        logger.info(f"Retrieved pricing from {len(pricing_options.options)} vendors for product {product_id}")
        return pricing_options

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product vendor pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get vendor pricing"
        )


# Vendor pricing management endpoints
@router.post("/products", response_model=PricingTierResponse)
async def create_product_pricing(
    pricing_data: PricingTierCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create pricing tier for a product.
    
    Allows vendors to set pricing for their products with
    quantity tiers, delivery fees, and special conditions.
    """
    try:
        # Only vendors can create pricing
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create product pricing"
            )

        pricing_service = PricingService(db)
        pricing_tier = await pricing_service.create_pricing_tier(
            pricing_data=pricing_data,
            vendor_user_id=current_user["user_id"]
        )
        
        logger.info(f"Created pricing tier {pricing_tier.id} for vendor {current_user['user_id']}")
        return pricing_tier

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating product pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product pricing"
        )


@router.get("/products", response_model=List[PricingTierResponse])
async def get_vendor_pricing(
    vendor_id: Optional[str] = Query(None, description="Vendor ID (admin only)"),
    product_id: Optional[str] = Query(None, description="Filter by product ID"),
    active_only: bool = Query(True, description="Show only active pricing"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get vendor's product pricing tiers.
    
    Returns all pricing tiers for the vendor's products
    with filtering options.
    """
    try:
        pricing_service = PricingService(db)
        
        # Determine which vendor's pricing to retrieve
        target_vendor_id = vendor_id
        if current_user["role"] == UserRole.VENDOR:
            # Vendors can only see their own pricing
            vendor = await pricing_service.get_vendor_by_user_id(current_user["user_id"])
            if not vendor:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vendor profile not found"
                )
            target_vendor_id = vendor.id
        elif vendor_id and current_user["role"] not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to view other vendor's pricing"
            )

        pricing_tiers = await pricing_service.get_vendor_pricing_tiers(
            vendor_id=target_vendor_id,
            product_id=product_id,
            active_only=active_only
        )
        
        logger.info(f"Retrieved {len(pricing_tiers)} pricing tiers for vendor {target_vendor_id}")
        return pricing_tiers

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving vendor pricing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vendor pricing"
        )


@router.put("/products/{pricing_id}", response_model=PricingTierResponse)
async def update_product_pricing(
    pricing_id: str,
    pricing_data: PricingTierUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update product pricing tier.
    
    Allows vendors to modify their pricing tiers,
    including prices, fees, and validity periods.
    """
    try:
        pricing_service = PricingService(db)
        
        # Get existing pricing tier
        pricing_tier = await pricing_service.get_pricing_tier_by_id(pricing_id)
        if not pricing_tier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pricing tier not found"
            )

        # Check permissions
        if current_user["role"] == UserRole.VENDOR:
            # Vendors can only update their own pricing
            vendor = await pricing_service.get_vendor_by_user_id(current_user["user_id"])
            if not vendor or pricing_tier.vendor_id != vendor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update your own pricing"
                )
        elif current_user["role"] not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to update pricing"
            )

        updated_pricing = await pricing_service.update_pricing_tier(pricing_id, pricing_data)
        
        logger.info(f"Updated pricing tier {pricing_id} by user {current_user['user_id']}")
        return updated_pricing

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating pricing tier {pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update pricing tier"
        )


@router.delete("/products/{pricing_id}")
async def delete_product_pricing(
    pricing_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete product pricing tier.
    
    Allows vendors to remove pricing tiers for their products.
    """
    try:
        pricing_service = PricingService(db)
        
        # Get existing pricing tier
        pricing_tier = await pricing_service.get_pricing_tier_by_id(pricing_id)
        if not pricing_tier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pricing tier not found"
            )

        # Check permissions
        if current_user["role"] == UserRole.VENDOR:
            # Vendors can only delete their own pricing
            vendor = await pricing_service.get_vendor_by_user_id(current_user["user_id"])
            if not vendor or pricing_tier.vendor_id != vendor.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete your own pricing"
                )
        elif current_user["role"] not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to delete pricing"
            )

        await pricing_service.delete_pricing_tier(pricing_id)
        
        logger.info(f"Deleted pricing tier {pricing_id} by user {current_user['user_id']}")
        return {"message": "Pricing tier deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pricing tier {pricing_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete pricing tier"
        )
