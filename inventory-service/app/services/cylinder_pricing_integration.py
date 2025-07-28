from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from decimal import Decimal
import httpx
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.cylinder import Cylinder, CylinderCondition
from app.schemas.cylinder import CylinderAllocationRequest, CylinderAllocationOption
from shared.models import CylinderSize

logger = logging.getLogger(__name__)


class CylinderPricingIntegration:
    """Integration service for cylinder-specific pricing with the pricing service."""

    def __init__(self, pricing_service_url: str = "http://pricing-service:8006"):
        self.pricing_service_url = pricing_service_url
        self.timeout = 30.0

    async def get_cylinder_pricing(
        self, 
        cylinder_ids: List[str], 
        quantity: int,
        hospital_latitude: float,
        hospital_longitude: float,
        is_emergency: bool = False
    ) -> Dict[str, Any]:
        """Get pricing for specific cylinders from the pricing service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                pricing_request = {
                    "cylinder_ids": cylinder_ids,
                    "quantity": quantity,
                    "latitude": hospital_latitude,
                    "longitude": hospital_longitude,
                    "include_emergency_pricing": is_emergency,
                    "sort_by": "price"
                }
                
                response = await client.post(
                    f"{self.pricing_service_url}/api/v1/pricing/cylinders/compare",
                    json=pricing_request
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Pricing service error: {response.status_code} - {response.text}")
                    return self._get_fallback_pricing(cylinder_ids, quantity, is_emergency)

        except Exception as e:
            logger.error(f"Error getting cylinder pricing: {e}")
            return self._get_fallback_pricing(cylinder_ids, quantity, is_emergency)

    async def enhance_allocation_with_pricing(
        self, 
        allocation_options: List[CylinderAllocationOption],
        allocation_request: CylinderAllocationRequest
    ) -> List[CylinderAllocationOption]:
        """Enhance allocation options with detailed pricing from pricing service."""
        try:
            enhanced_options = []
            
            for option in allocation_options:
                # Get detailed pricing for this option
                pricing_data = await self.get_cylinder_pricing(
                    option.available_cylinders,
                    allocation_request.quantity,
                    float(allocation_request.delivery_latitude),
                    float(allocation_request.delivery_longitude),
                    allocation_request.is_emergency
                )
                
                # Update option with pricing details
                if pricing_data and "pricing_options" in pricing_data:
                    pricing_option = pricing_data["pricing_options"][0]  # Best pricing option
                    
                    option.total_cost = Decimal(str(pricing_option.get("total_price", option.total_cost)))
                    option.currency = pricing_option.get("currency", "NGN")
                    
                    # Add pricing breakdown to metadata
                    option.pricing_breakdown = {
                        "unit_price": pricing_option.get("unit_price", 0),
                        "subtotal": pricing_option.get("subtotal", 0),
                        "delivery_fee": pricing_option.get("delivery_fee", 0),
                        "setup_fee": pricing_option.get("setup_fee", 0),
                        "handling_fee": pricing_option.get("handling_fee", 0),
                        "emergency_surcharge": pricing_option.get("emergency_surcharge", 0),
                        "total_discount": pricing_option.get("total_discount", 0),
                        "payment_terms": pricing_option.get("payment_terms", "immediate")
                    }
                
                enhanced_options.append(option)
            
            return enhanced_options

        except Exception as e:
            logger.error(f"Error enhancing allocation with pricing: {e}")
            return allocation_options  # Return original options if pricing fails

    async def calculate_cylinder_condition_pricing(
        self, 
        cylinders: List[Cylinder],
        base_price: Decimal
    ) -> Dict[str, Decimal]:
        """Calculate pricing adjustments based on cylinder condition."""
        
        condition_multipliers = {
            CylinderCondition.EXCELLENT: Decimal("1.0"),
            CylinderCondition.GOOD: Decimal("0.95"),
            CylinderCondition.FAIR: Decimal("0.85"),
            CylinderCondition.POOR: Decimal("0.70"),
            CylinderCondition.DAMAGED: Decimal("0.50"),
            CylinderCondition.UNSAFE: Decimal("0.0")
        }
        
        cylinder_pricing = {}
        
        for cylinder in cylinders:
            multiplier = condition_multipliers.get(cylinder.condition, Decimal("1.0"))
            adjusted_price = base_price * multiplier
            
            # Additional adjustments based on fill level
            fill_adjustment = cylinder.fill_level_percentage / 100
            final_price = adjusted_price * fill_adjustment
            
            cylinder_pricing[str(cylinder.id)] = final_price
        
        return cylinder_pricing

    async def get_dynamic_pricing(
        self, 
        cylinder_size: CylinderSize,
        vendor_id: str,
        location_latitude: float,
        location_longitude: float,
        hospital_latitude: float,
        hospital_longitude: float,
        quantity: int,
        is_emergency: bool = False
    ) -> Dict[str, Any]:
        """Get dynamic pricing based on demand, distance, and market conditions."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                pricing_request = {
                    "product_category": "oxygen_cylinder",
                    "cylinder_size": cylinder_size.value,
                    "vendor_id": vendor_id,
                    "quantity": quantity,
                    "pickup_latitude": location_latitude,
                    "pickup_longitude": location_longitude,
                    "delivery_latitude": hospital_latitude,
                    "delivery_longitude": hospital_longitude,
                    "include_emergency_pricing": is_emergency,
                    "include_market_analysis": True
                }
                
                response = await client.post(
                    f"{self.pricing_service_url}/api/v1/pricing/dynamic",
                    json=pricing_request
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Dynamic pricing error: {response.status_code}")
                    return self._get_fallback_dynamic_pricing(cylinder_size, quantity, is_emergency)

        except Exception as e:
            logger.error(f"Error getting dynamic pricing: {e}")
            return self._get_fallback_dynamic_pricing(cylinder_size, quantity, is_emergency)

    async def calculate_bulk_discount(
        self, 
        cylinder_count: int,
        base_total: Decimal,
        vendor_id: str
    ) -> Dict[str, Any]:
        """Calculate bulk discounts for large cylinder orders."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                discount_request = {
                    "vendor_id": vendor_id,
                    "item_count": cylinder_count,
                    "base_total": float(base_total),
                    "product_category": "oxygen_cylinder"
                }
                
                response = await client.post(
                    f"{self.pricing_service_url}/api/v1/pricing/bulk-discount",
                    json=discount_request
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return self._get_fallback_bulk_discount(cylinder_count, base_total)

        except Exception as e:
            logger.error(f"Error calculating bulk discount: {e}")
            return self._get_fallback_bulk_discount(cylinder_count, base_total)

    async def get_market_pricing_analysis(
        self, 
        cylinder_size: CylinderSize,
        geographic_area: str
    ) -> Dict[str, Any]:
        """Get market pricing analysis for competitive pricing."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.pricing_service_url}/api/v1/pricing/market-analysis",
                    params={
                        "product_category": "oxygen_cylinder",
                        "cylinder_size": cylinder_size.value,
                        "geographic_area": geographic_area
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    return self._get_fallback_market_analysis(cylinder_size)

        except Exception as e:
            logger.error(f"Error getting market analysis: {e}")
            return self._get_fallback_market_analysis(cylinder_size)

    def _get_fallback_pricing(self, cylinder_ids: List[str], quantity: int, is_emergency: bool) -> Dict[str, Any]:
        """Fallback pricing when pricing service is unavailable."""
        base_price = Decimal("150.0")  # Base price per cylinder
        delivery_fee = Decimal("50.0")
        
        if is_emergency:
            emergency_surcharge = base_price * Decimal("0.5")
        else:
            emergency_surcharge = Decimal("0.0")
        
        subtotal = base_price * quantity
        total_price = subtotal + delivery_fee + emergency_surcharge
        
        return {
            "pricing_options": [{
                "cylinder_ids": cylinder_ids,
                "unit_price": float(base_price),
                "quantity": quantity,
                "subtotal": float(subtotal),
                "delivery_fee": float(delivery_fee),
                "emergency_surcharge": float(emergency_surcharge),
                "total_price": float(total_price),
                "currency": "NGN",
                "payment_terms": "immediate"
            }],
            "fallback_pricing": True
        }

    def _get_fallback_dynamic_pricing(self, cylinder_size: CylinderSize, quantity: int, is_emergency: bool) -> Dict[str, Any]:
        """Fallback dynamic pricing."""
        size_multipliers = {
            CylinderSize.SMALL: Decimal("1.0"),
            CylinderSize.MEDIUM: Decimal("1.2"),
            CylinderSize.LARGE: Decimal("1.5"),
            CylinderSize.EXTRA_LARGE: Decimal("1.8")
        }
        
        base_price = Decimal("150.0") * size_multipliers.get(cylinder_size, Decimal("1.0"))
        
        if is_emergency:
            base_price *= Decimal("1.5")
        
        return {
            "unit_price": float(base_price),
            "total_price": float(base_price * quantity),
            "currency": "NGN",
            "demand_factor": 1.0,
            "distance_factor": 1.0,
            "market_factor": 1.0,
            "fallback_pricing": True
        }

    def _get_fallback_bulk_discount(self, cylinder_count: int, base_total: Decimal) -> Dict[str, Any]:
        """Fallback bulk discount calculation."""
        if cylinder_count >= 50:
            discount_percentage = Decimal("0.15")  # 15% for 50+
        elif cylinder_count >= 20:
            discount_percentage = Decimal("0.10")  # 10% for 20+
        elif cylinder_count >= 10:
            discount_percentage = Decimal("0.05")  # 5% for 10+
        else:
            discount_percentage = Decimal("0.0")
        
        discount_amount = base_total * discount_percentage
        final_total = base_total - discount_amount
        
        return {
            "discount_percentage": float(discount_percentage * 100),
            "discount_amount": float(discount_amount),
            "final_total": float(final_total),
            "currency": "NGN",
            "fallback_pricing": True
        }

    def _get_fallback_market_analysis(self, cylinder_size: CylinderSize) -> Dict[str, Any]:
        """Fallback market analysis."""
        size_base_prices = {
            CylinderSize.SMALL: 120.0,
            CylinderSize.MEDIUM: 150.0,
            CylinderSize.LARGE: 200.0,
            CylinderSize.EXTRA_LARGE: 250.0
        }
        
        base_price = size_base_prices.get(cylinder_size, 150.0)
        
        return {
            "average_price": base_price,
            "minimum_price": base_price * 0.8,
            "maximum_price": base_price * 1.3,
            "vendor_count": 5,
            "price_trend": "stable",
            "fallback_analysis": True
        }
