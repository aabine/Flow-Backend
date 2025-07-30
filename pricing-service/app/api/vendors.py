from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.core.database import get_db
from app.schemas.vendor import (
    VendorResponse, VendorListResponse, VendorSearchRequest,
    ServiceAreaResponse, VendorCreate, VendorUpdate
)
from app.services.vendor_service import VendorService
from shared.security.auth import get_current_user
from shared.models import UserRole

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/public/nearby", response_model=VendorListResponse)
async def get_public_nearby_vendors(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude coordinate"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude coordinate"),
    radius_km: float = Query(50.0, gt=0, le=200, description="Search radius in kilometers"),
    business_type: Optional[str] = Query(None, description="Filter by business type"),
    verification_status: Optional[str] = Query("verified", description="Filter by verification status"),
    minimum_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum vendor rating"),
    emergency_delivery: Optional[bool] = Query(None, description="Filter vendors with emergency delivery"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get nearby vendors for public browsing (no authentication required).

    This endpoint allows potential users to discover vendors in their area
    without requiring registration or authentication.
    """
    try:
        search_request = VendorSearchRequest(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            business_type=business_type,
            verification_status=verification_status,
            minimum_rating=minimum_rating,
            emergency_delivery=emergency_delivery,
            page=page,
            page_size=page_size
        )

        vendor_service = VendorService()
        vendors = await vendor_service.search_nearby_vendors(db, search_request)

        return vendors
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get public nearby vendors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get nearby vendors: {str(e)}"
        )


@router.get("/nearby", response_model=VendorListResponse)
async def get_nearby_vendors(
    latitude: float = Query(..., ge=-90, le=90, description="Latitude coordinate"),
    longitude: float = Query(..., ge=-180, le=180, description="Longitude coordinate"),
    radius_km: float = Query(50.0, gt=0, le=200, description="Search radius in kilometers"),
    business_type: Optional[str] = Query(None, description="Filter by business type"),
    verification_status: Optional[str] = Query("verified", description="Filter by verification status"),
    minimum_rating: Optional[float] = Query(None, ge=0, le=5, description="Minimum vendor rating"),
    emergency_delivery: Optional[bool] = Query(None, description="Filter vendors with emergency delivery"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get nearby vendors based on geographical location.
    
    This endpoint allows hospitals to discover vendors in their area
    with filtering options for business type, ratings, and services.
    """
    try:
        # Only hospitals can search for vendors
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can search for vendors"
            )

        search_request = VendorSearchRequest(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            business_type=business_type,
            verification_status=verification_status,
            minimum_rating=minimum_rating,
            emergency_delivery=emergency_delivery,
            page=page,
            page_size=page_size
        )

        vendor_service = VendorService(db)
        result = await vendor_service.search_nearby_vendors(search_request)
        
        logger.info(f"Found {result.total} vendors for hospital {current_user['user_id']} within {radius_km}km")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching nearby vendors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search vendors"
        )


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor_details(
    vendor_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific vendor.
    
    Returns comprehensive vendor information including business details,
    ratings, certifications, and operational information.
    """
    try:
        vendor_service = VendorService(db)
        vendor = await vendor_service.get_vendor_by_id(vendor_id)
        
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor not found"
            )

        logger.info(f"Retrieved vendor details for {vendor_id} by user {current_user['user_id']}")
        return vendor

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vendor details"
        )


@router.get("/{vendor_id}/service-areas", response_model=List[ServiceAreaResponse])
async def get_vendor_service_areas(
    vendor_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get service areas covered by a specific vendor.
    
    Returns all geographical areas where the vendor provides services,
    including delivery fees and estimated delivery times.
    """
    try:
        vendor_service = VendorService(db)
        
        # Verify vendor exists
        vendor = await vendor_service.get_vendor_by_id(vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor not found"
            )

        service_areas = await vendor_service.get_vendor_service_areas(vendor_id)
        
        logger.info(f"Retrieved {len(service_areas)} service areas for vendor {vendor_id}")
        return service_areas

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving service areas for vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vendor service areas"
        )


@router.post("/", response_model=VendorResponse)
async def create_vendor(
    vendor_data: VendorCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new vendor profile.
    
    This endpoint allows users with vendor role to create their vendor profile
    after registering as a user in the system.
    """
    try:
        # Only vendors can create vendor profiles
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create vendor profiles"
            )

        # Ensure the vendor is creating their own profile
        if vendor_data.user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only create your own vendor profile"
            )

        vendor_service = VendorService(db)
        
        # Check if vendor profile already exists
        existing_vendor = await vendor_service.get_vendor_by_user_id(vendor_data.user_id)
        if existing_vendor:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vendor profile already exists for this user"
            )

        vendor = await vendor_service.create_vendor(vendor_data)
        
        logger.info(f"Created vendor profile {vendor.id} for user {current_user['user_id']}")
        return vendor

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating vendor profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create vendor profile"
        )


@router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: str,
    vendor_data: VendorUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update vendor information.
    
    Allows vendors to update their business information and operational details.
    """
    try:
        vendor_service = VendorService(db)
        
        # Get existing vendor
        vendor = await vendor_service.get_vendor_by_id(vendor_id)
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor not found"
            )

        # Check permissions
        if current_user["role"] == UserRole.VENDOR:
            # Vendors can only update their own profile
            if vendor.user_id != current_user["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update your own vendor profile"
                )
        elif current_user["role"] not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to update vendor"
            )

        updated_vendor = await vendor_service.update_vendor(vendor_id, vendor_data)
        
        logger.info(f"Updated vendor {vendor_id} by user {current_user['user_id']}")
        return updated_vendor

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating vendor {vendor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vendor"
        )
