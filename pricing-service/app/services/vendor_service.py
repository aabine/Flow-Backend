from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from decimal import Decimal
import logging
import math

from app.models.vendor import Vendor, VendorProfile, ServiceArea
from app.schemas.vendor import (
    VendorCreate, VendorUpdate, VendorResponse, VendorListResponse,
    VendorSearchRequest, ServiceAreaResponse
)
from app.services.event_service import event_service

logger = logging.getLogger(__name__)


class VendorService:
    """Service for vendor management operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def search_nearby_vendors(self, search_request: VendorSearchRequest) -> VendorListResponse:
        """Search for vendors near a specific location."""
        try:
            # Build base query
            query = select(Vendor).options(
                selectinload(Vendor.service_areas),
                selectinload(Vendor.vendor_profile)
            )
            
            # Apply filters
            filters = [Vendor.is_active == True]
            
            if search_request.verification_status:
                filters.append(Vendor.verification_status == search_request.verification_status)
            
            if search_request.business_type:
                filters.append(Vendor.business_type == search_request.business_type)
            
            if search_request.minimum_rating:
                filters.append(Vendor.average_rating >= search_request.minimum_rating)
            
            query = query.where(and_(*filters))
            
            # Execute query to get all vendors first
            result = await self.db.execute(query)
            all_vendors = result.scalars().all()
            
            # Filter by distance and emergency delivery
            nearby_vendors = []
            for vendor in all_vendors:
                # Check if vendor serves the requested location
                serves_location, distance = await self._check_vendor_serves_location(
                    vendor, search_request.latitude, search_request.longitude, search_request.radius_km
                )
                
                if serves_location:
                    # Check emergency delivery filter
                    if search_request.emergency_delivery is not None:
                        has_emergency = any(
                            area.emergency_delivery_available 
                            for area in vendor.service_areas
                        )
                        if search_request.emergency_delivery and not has_emergency:
                            continue
                    
                    vendor_response = await self._vendor_to_response(vendor, distance)
                    nearby_vendors.append(vendor_response)
            
            # Sort by distance
            nearby_vendors.sort(key=lambda v: getattr(v, 'distance_km', float('inf')) or float('inf'))
            
            # Apply pagination
            total = len(nearby_vendors)
            start_idx = (search_request.page - 1) * search_request.page_size
            end_idx = start_idx + search_request.page_size
            paginated_vendors = nearby_vendors[start_idx:end_idx]
            
            total_pages = math.ceil(total / search_request.page_size)
            
            return VendorListResponse(
                vendors=paginated_vendors,
                total=total,
                page=search_request.page,
                page_size=search_request.page_size,
                total_pages=total_pages
            )
            
        except Exception as e:
            logger.error(f"Error searching nearby vendors: {e}")
            raise
    
    async def get_vendor_by_id(self, vendor_id: str) -> Optional[VendorResponse]:
        """Get vendor by ID."""
        try:
            query = select(Vendor).options(
                selectinload(Vendor.service_areas),
                selectinload(Vendor.vendor_profile)
            ).where(Vendor.id == vendor_id)
            
            result = await self.db.execute(query)
            vendor = result.scalar_one_or_none()
            
            if vendor:
                return await self._vendor_to_response(vendor)
            return None
            
        except Exception as e:
            logger.error(f"Error getting vendor by ID {vendor_id}: {e}")
            raise
    
    async def get_vendor_by_user_id(self, user_id: str) -> Optional[VendorResponse]:
        """Get vendor by user ID."""
        try:
            query = select(Vendor).options(
                selectinload(Vendor.service_areas),
                selectinload(Vendor.vendor_profile)
            ).where(Vendor.user_id == user_id)
            
            result = await self.db.execute(query)
            vendor = result.scalar_one_or_none()
            
            if vendor:
                return await self._vendor_to_response(vendor)
            return None
            
        except Exception as e:
            logger.error(f"Error getting vendor by user ID {user_id}: {e}")
            raise
    
    async def get_vendor_service_areas(self, vendor_id: str) -> List[ServiceAreaResponse]:
        """Get service areas for a vendor."""
        try:
            query = select(ServiceArea).where(
                and_(
                    ServiceArea.vendor_id == vendor_id,
                    ServiceArea.is_active == True
                )
            )
            
            result = await self.db.execute(query)
            service_areas = result.scalars().all()
            
            return [
                ServiceAreaResponse(
                    id=str(area.id),
                    vendor_id=str(area.vendor_id),
                    area_name=area.area_name,
                    area_type=area.area_type,
                    center_latitude=area.center_latitude,
                    center_longitude=area.center_longitude,
                    radius_km=area.radius_km,
                    state=area.state,
                    cities=area.cities,
                    delivery_fee=area.delivery_fee,
                    minimum_order_value=area.minimum_order_value,
                    estimated_delivery_time_hours=area.estimated_delivery_time_hours,
                    emergency_delivery_available=area.emergency_delivery_available,
                    emergency_delivery_time_hours=area.emergency_delivery_time_hours,
                    boundary_coordinates=area.boundary_coordinates,
                    postal_codes=area.postal_codes,
                    is_active=area.is_active,
                    priority_level=area.priority_level,
                    created_at=area.created_at,
                    updated_at=area.updated_at
                )
                for area in service_areas
            ]
            
        except Exception as e:
            logger.error(f"Error getting service areas for vendor {vendor_id}: {e}")
            raise
    
    async def create_vendor(self, vendor_data: VendorCreate) -> VendorResponse:
        """Create a new vendor."""
        try:
            vendor = Vendor(
                user_id=vendor_data.user_id,
                business_name=vendor_data.business_name,
                business_registration_number=vendor_data.business_registration_number,
                tax_identification_number=vendor_data.tax_identification_number,
                contact_person=vendor_data.contact_person,
                contact_phone=vendor_data.contact_phone,
                contact_email=vendor_data.contact_email,
                business_address=vendor_data.business_address,
                business_city=vendor_data.business_city,
                business_state=vendor_data.business_state,
                business_country=vendor_data.business_country,
                postal_code=vendor_data.postal_code,
                business_type=vendor_data.business_type,
                years_in_business=vendor_data.years_in_business,
                license_number=vendor_data.license_number,
                emergency_contact=vendor_data.emergency_contact,
                emergency_surcharge_percentage=vendor_data.emergency_surcharge_percentage,
                minimum_order_value=vendor_data.minimum_order_value
            )
            
            self.db.add(vendor)
            await self.db.commit()
            await self.db.refresh(vendor)
            
            # Publish vendor added event
            await event_service.publish_vendor_added(
                str(vendor.id),
                {
                    "business_name": vendor.business_name,
                    "business_type": vendor.business_type,
                    "business_city": vendor.business_city,
                    "business_state": vendor.business_state,
                    "business_country": vendor.business_country
                }
            )
            
            return await self._vendor_to_response(vendor)
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating vendor: {e}")
            raise
    
    async def update_vendor(self, vendor_id: str, vendor_data: VendorUpdate) -> VendorResponse:
        """Update vendor information."""
        try:
            query = select(Vendor).where(Vendor.id == vendor_id)
            result = await self.db.execute(query)
            vendor = result.scalar_one_or_none()
            
            if not vendor:
                raise ValueError("Vendor not found")
            
            # Update fields
            update_data = vendor_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(vendor, field, value)
            
            await self.db.commit()
            await self.db.refresh(vendor)
            
            return await self._vendor_to_response(vendor)
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating vendor {vendor_id}: {e}")
            raise

    async def _check_vendor_serves_location(self, vendor: Vendor, latitude: float,
                                          longitude: float, max_radius: float) -> tuple[bool, Optional[float]]:
        """Check if vendor serves a specific location and return distance."""
        min_distance = float('inf')
        serves_location = False

        for service_area in vendor.service_areas:
            if not service_area.is_active:
                continue

            if service_area.area_type == "radius" and service_area.center_latitude and service_area.center_longitude:
                # Calculate distance for radius-based service areas
                distance = self._calculate_distance(
                    latitude, longitude,
                    float(service_area.center_latitude), float(service_area.center_longitude)
                )

                if distance <= float(service_area.radius_km) and distance <= max_radius:
                    serves_location = True
                    min_distance = min(min_distance, distance)

            elif service_area.area_type in ["city", "state"]:
                # For city/state areas, use vendor's business location as reference
                if vendor.business_city and vendor.business_state:
                    # This is a simplified check - in production, you'd use proper geocoding
                    serves_location = True
                    # Use a default distance for city/state areas
                    min_distance = min(min_distance, 25.0)

        return serves_location, min_distance if serves_location else None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula."""
        R = 6371  # Earth's radius in kilometers

        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    async def _vendor_to_response(self, vendor: Vendor, distance: Optional[float] = None) -> VendorResponse:
        """Convert vendor model to response schema."""
        response_data = {
            "id": str(vendor.id),
            "user_id": str(vendor.user_id),
            "business_name": vendor.business_name,
            "business_registration_number": vendor.business_registration_number,
            "tax_identification_number": vendor.tax_identification_number,
            "contact_person": vendor.contact_person,
            "contact_phone": vendor.contact_phone,
            "contact_email": vendor.contact_email,
            "business_address": vendor.business_address,
            "business_city": vendor.business_city,
            "business_state": vendor.business_state,
            "business_country": vendor.business_country,
            "postal_code": vendor.postal_code,
            "business_type": vendor.business_type,
            "years_in_business": vendor.years_in_business,
            "license_number": vendor.license_number,
            "emergency_contact": vendor.emergency_contact,
            "emergency_surcharge_percentage": vendor.emergency_surcharge_percentage,
            "minimum_order_value": vendor.minimum_order_value,
            "verification_status": vendor.verification_status,
            "is_active": vendor.is_active,
            "is_featured": vendor.is_featured,
            "average_rating": vendor.average_rating,
            "total_orders": vendor.total_orders,
            "successful_deliveries": vendor.successful_deliveries,
            "response_time_hours": vendor.response_time_hours,
            "operating_hours": vendor.operating_hours,
            "created_at": vendor.created_at,
            "updated_at": vendor.updated_at,
            "verified_at": vendor.verified_at,
            "last_active_at": vendor.last_active_at
        }

        # Add distance if provided
        if distance is not None:
            response_data["distance_km"] = distance

        return VendorResponse(**response_data)
