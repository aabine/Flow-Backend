"""
Service-to-Service Authentication Module
Handles authentication for Order service to communicate with other microservices
Uses header-based authentication as per Flow-Backend platform standards
"""

import os
import httpx
import secrets
from typing import Dict, Optional, Any
import logging
import sys

# Add shared modules to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.resilience.circuit_breaker import CircuitBreakerConfig, circuit_breaker_manager
from shared.resilience.retry import RetryConfig, RetryHandler, RetryConfigs

logger = logging.getLogger(__name__)


class ServiceAuthManager:
    """Manages authentication for service-to-service communication using platform headers."""

    def __init__(self):
        self.api_gateway_url = os.getenv("API_GATEWAY_URL", "http://localhost:8000")
        self.inventory_service_url = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8004")
        self.pricing_service_url = os.getenv("PRICING_SERVICE_URL", "http://localhost:8006")
        self.notification_service_url = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010")

        # Service URLs for direct communication (fallback)
        self.service_urls = {
            "inventory": self.inventory_service_url,
            "pricing": self.pricing_service_url,
            "notification": self.notification_service_url
        }

        # Initialize resilience patterns
        self._setup_circuit_breakers()
        self.retry_handler = RetryHandler(RetryConfigs.HTTP)

    def _setup_circuit_breakers(self):
        """Setup circuit breakers for each service."""
        # Circuit breaker configuration for external services
        cb_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30,
            success_threshold=2,
            timeout=10.0
        )

        # Create circuit breakers for each service
        self.inventory_cb = circuit_breaker_manager.get_circuit_breaker("inventory-service", cb_config)
        self.pricing_cb = circuit_breaker_manager.get_circuit_breaker("pricing-service", cb_config)
        self.notification_cb = circuit_breaker_manager.get_circuit_breaker("notification-service", cb_config)

    def get_authenticated_headers(self, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Get headers for authenticated service calls using platform header-based authentication.

        Args:
            user_context: User context containing user_id and role from authenticated request

        Returns:
            Dict with authentication headers following platform standards
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "order-service/1.0",
            "X-Request-ID": secrets.token_urlsafe(16)  # For request tracing
        }

        # Add user context headers if available (from authenticated request)
        if user_context:
            if user_context.get("user_id"):
                headers["X-User-ID"] = str(user_context["user_id"])
            if user_context.get("role"):
                # Convert role enum to string if needed
                role = user_context["role"]
                if hasattr(role, 'value'):
                    headers["X-User-Role"] = role.value
                else:
                    headers["X-User-Role"] = str(role)
        else:
            # For service-to-service calls without user context, use service identity
            headers["X-User-ID"] = "order-service"
            headers["X-User-Role"] = "SERVICE"

        return headers

    def get_service_url(self, service: str, path: str) -> str:
        """
        Get the direct service URL for a service endpoint.
        Uses direct service communication for better performance and reliability.
        """
        # Remove leading slash from path if present
        path = path.lstrip("/")

        base_url = self.service_urls.get(service)
        if not base_url:
            logger.warning(f"Unknown service: {service}, available services: {list(self.service_urls.keys())}")
            return f"http://localhost:8000/{service}/{path}"  # Fallback to API gateway

        return f"{base_url}/{path}"

    async def make_authenticated_request(
        self,
        method: str,
        service: str,
        path: str,
        user_context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Make an authenticated request to another service using header-based authentication.
        Includes circuit breaker and retry logic for resilience.

        Args:
            method: HTTP method (GET, POST, etc.)
            service: Target service name (inventory, pricing, etc.)
            path: Service endpoint path
            user_context: User context for authentication headers
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response: Response from the target service
        """
        # Get appropriate circuit breaker for the service
        circuit_breaker = self._get_circuit_breaker(service)

        # Define the actual request function
        async def make_request():
            url = self.get_service_url(service, path)
            headers = self.get_authenticated_headers(user_context)

            # Merge with any provided headers
            if "headers" in kwargs:
                headers.update(kwargs["headers"])
            kwargs["headers"] = headers

            # Add timeout if not specified
            if "timeout" not in kwargs:
                kwargs["timeout"] = 10.0

            logger.info(
                f"Making {method} request to {service} service: {path}",
                extra={
                    "service": service,
                    "method": method,
                    "path": path,
                    "url": url,
                    "correlation_id": user_context.get("correlation_id") if user_context else None
                }
            )

            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, **kwargs)

                if response.status_code >= 400:
                    logger.warning(
                        f"Request failed: {method} {url} -> {response.status_code}",
                        extra={
                            "service": service,
                            "method": method,
                            "path": path,
                            "status_code": response.status_code,
                            "response_text": response.text[:500]  # Limit response text
                        }
                    )
                    # Raise exception for 5xx errors to trigger circuit breaker
                    if response.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"Server error: {response.status_code}",
                            request=response.request,
                            response=response
                        )
                else:
                    logger.debug(f"Request successful: {method} {url} -> {response.status_code}")

                return response

        # Execute with circuit breaker and retry
        try:
            if circuit_breaker:
                # Use circuit breaker with retry
                return await self.retry_handler.execute(circuit_breaker.call, make_request)
            else:
                # Use retry only
                return await self.retry_handler.execute(make_request)

        except Exception as e:
            logger.error(
                f"Request failed after all retries: {method} {service}/{path}",
                extra={
                    "service": service,
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "correlation_id": user_context.get("correlation_id") if user_context else None
                }
            )
            raise

    def _get_circuit_breaker(self, service: str):
        """Get circuit breaker for a specific service."""
        circuit_breakers = {
            "inventory": self.inventory_cb,
            "pricing": self.pricing_cb,
            "notification": self.notification_cb
        }
        return circuit_breakers.get(service)


# Global instance
service_auth = ServiceAuthManager()


class ServiceClient:
    """High-level client for making service calls with header-based authentication."""

    def __init__(self, auth_manager: ServiceAuthManager = None):
        self.auth = auth_manager or service_auth

    async def get_inventory_availability(
        self,
        vendor_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Get vendor availability from inventory service."""
        try:
            response = await self.auth.make_authenticated_request(
                "GET",
                "inventory",
                f"vendors/{vendor_id}/availability",
                user_context=user_context
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.info(f"Vendor {vendor_id} not found")
                return {"available": False, "message": "Vendor not found"}
            else:
                logger.error(f"Failed to get vendor availability: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting vendor availability: {str(e)}")
            return None

    async def search_nearby_catalog(
        self,
        latitude: float,
        longitude: float,
        max_distance_km: float = 50.0,
        is_emergency: bool = False,
        sort_by: str = "distance",
        user_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Search nearby catalog from inventory service."""
        try:
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "max_distance_km": max_distance_km,
                "is_emergency": is_emergency,
                "sort_by": sort_by
            }

            response = await self.auth.make_authenticated_request(
                "GET",
                "inventory",
                "catalog/nearby",
                user_context=user_context,
                params=params
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to search catalog: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error searching catalog: {str(e)}")
            return None

    async def create_stock_reservation(
        self,
        cylinder_size: str,
        quantity: int,
        order_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Create stock reservation in inventory service."""
        try:
            reservation_data = {
                "cylinder_size": cylinder_size,
                "quantity": quantity,
                "order_id": order_id
            }

            response = await self.auth.make_authenticated_request(
                "POST",
                "inventory",
                "inventory/reservations",
                user_context=user_context,
                json=reservation_data
            )

            if response.status_code in [200, 201]:
                return response.json()
            else:
                logger.error(f"Failed to create reservation: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating reservation: {str(e)}")
            return None


# Global service client instance
service_client = ServiceClient()
