from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import httpx
import os
import sys
import logging
from typing import Optional, List
import json
import time
from datetime import datetime
import secrets

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add shared directory to path for security modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

try:
    from security.auth import JWTManager, SecurityConfig
    from security.middleware import (
        RateLimitMiddleware, SecurityHeadersMiddleware,
        InputValidationMiddleware, IPWhitelistMiddleware
    )
    from security.encryption import data_masking
    from models import UserRole

    # Initialize JWT manager
    jwt_manager = JWTManager()
    SECURITY_MODULES_AVAILABLE = True

except ImportError as e:
    logger.warning(f"Security modules not available: {e}")
    SECURITY_MODULES_AVAILABLE = False

    # Fallback implementations
    class UserRole:
        ADMIN = "admin"
        HOSPITAL = "hospital"
        VENDOR = "vendor"

    class DataMasking:
        @staticmethod
        def mask_sensitive_dict(data):
            return data  # Simple fallback

    class SecurityConfig:
        SECURITY_HEADERS = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "X-Permitted-Cross-Domain-Policies": "none",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }

    data_masking = DataMasking()
    jwt_manager = None

app = FastAPI(
    title="Oxygen Supply Platform API Gateway",
    description="Secure Central API Gateway for the Oxygen Supply Platform",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") != "production" else None
)

# Security Configuration
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ADMIN_IP_WHITELIST = os.getenv("ADMIN_IP_WHITELIST", "").split(",") if os.getenv("ADMIN_IP_WHITELIST") else []

# Add security middleware (order matters!)
if SECURITY_MODULES_AVAILABLE:
    logger.info("Adding security middleware...")
    app.add_middleware(IPWhitelistMiddleware, whitelist=ADMIN_IP_WHITELIST, admin_only=True)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(InputValidationMiddleware, max_request_size=10 * 1024 * 1024)  # 10MB
    app.add_middleware(RateLimitMiddleware, redis_url=REDIS_URL, default_rate_limit=60)
    logger.info("Security middleware enabled")
else:
    logger.warning("Security middleware disabled - shared security modules not available")

# CORS middleware with secure configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]
)

security = HTTPBearer()


# Security event logging
async def log_security_event(event_type: str, user_id: str, details: dict, request: Request):
    """Log security events for monitoring and audit purposes."""

    event_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "request_id": request.headers.get("x-request-id", "unknown"),
        "path": str(request.url.path),
        "method": request.method,
        "details": details
    }

    # Log to application logger
    logger.warning(f"SECURITY_EVENT: {event_type} - {json.dumps(event_data)}")

    # TODO: Send to security monitoring system (SIEM)
    # This could be enhanced to send to external monitoring systems
    try:
        # Example: Send to security monitoring endpoint
        # await send_to_security_monitoring(event_data)
        pass
    except Exception as e:
        logger.error(f"Failed to send security event to monitoring system: {e}")


# Enhanced role-based access control
def check_rbac_permissions(user_data: dict, service: str, method: str, path: str) -> bool:
    """Check if user has permission to access the requested resource."""

    user_role = user_data.get("role")
    if not user_role:
        return False

    permissions = ROLE_PERMISSIONS.get(user_role, {})

    # Check service access
    allowed_services = permissions.get("allowed_services", [])
    if "*" not in allowed_services and service not in allowed_services:
        return False

    # Check method access
    allowed_methods = permissions.get("allowed_methods", [])
    if "*" not in allowed_methods and method not in allowed_methods:
        return False

    # Check restricted endpoints
    restricted_endpoints = permissions.get("restricted_endpoints", [])
    for restricted in restricted_endpoints:
        if path.startswith(restricted):
            return False

    return True


# Service URLs from environment with HTTPS in production
def get_service_url(service_name: str, default_port: int) -> str:
    """Get service URL with proper protocol based on environment."""
    base_url = os.getenv(f"{service_name.upper()}_SERVICE_URL")
    if base_url:
        return base_url

    # Use HTTPS in production
    protocol = "https" if os.getenv("ENVIRONMENT") == "production" else "http"
    host = os.getenv("SERVICE_HOST", "localhost")

    return f"{protocol}://{host}:{default_port}"

SERVICE_URLS = {
    "user": get_service_url("user", 8001),
    "supplier_onboarding": get_service_url("supplier_onboarding", 8002),
    "location": get_service_url("location", 8003),
    "inventory": get_service_url("inventory", 8004),
    "order": get_service_url("order", 8005),
    "pricing": get_service_url("pricing", 8006),
    "delivery": get_service_url("delivery", 8007),
    "payment": get_service_url("payment", 8008),
    "review": get_service_url("review", 8009),
    "notification": get_service_url("notification", 8010),
    "admin": get_service_url("admin", 8011),
}

# Role-based access control configuration
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        "allowed_services": ["*"],  # Admin can access all services
        "allowed_methods": ["*"]
    },
    UserRole.HOSPITAL: {
        "allowed_services": ["user", "order", "pricing", "review", "notification", "inventory", "location", "payment"],
        "allowed_methods": ["GET", "POST", "PUT", "PATCH"],
        "restricted_endpoints": ["/admin/"]
    },
    UserRole.VENDOR: {
        "allowed_services": ["user", "inventory", "order", "pricing", "review", "notification", "location"],
        "allowed_methods": ["GET", "POST", "PUT", "PATCH"],
        "restricted_endpoints": ["/admin/", "/payment/admin/"]
    }
}


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token with enhanced security validation."""

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        # Try local JWT verification first if security modules are available
        if SECURITY_MODULES_AVAILABLE and jwt_manager:
            try:
                payload = jwt_manager.verify_token(credentials.credentials)

                # Extract user information
                user_data = {
                    "user_id": payload["sub"],
                    "role": payload["role"],
                    "permissions": payload.get("permissions", []),
                    "token_id": payload.get("jti"),
                    "issued_at": payload.get("iat"),
                    "expires_at": payload.get("exp")
                }

                # Log successful authentication (with masked token)
                masked_token = credentials.credentials[:10] + "..." + credentials.credentials[-10:]
                logger.info(f"Token verified locally for user {user_data['user_id']} with role {user_data['role']} (token: {masked_token})")

                return user_data

            except Exception as jwt_error:
                # If local verification fails, try with user service as fallback
                logger.warning(f"Local JWT verification failed: {str(jwt_error)}, trying user service fallback")

        # Fallback to user service verification
        async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{SERVICE_URLS['user']}/auth/verify-token",
                    headers={"Authorization": f"Bearer {credentials.credentials}"}
                )

                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"Token verified via user service for user {user_data.get('user_id')}")
                    return user_data
                else:
                    logger.warning(f"Token verification failed via user service: {response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid authentication credentials",
                        headers={"WWW-Authenticate": "Bearer"}
                    )

    except httpx.TimeoutException:
        logger.error("Authentication service timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service timeout"
        )
    except httpx.RequestError as e:
        logger.error(f"Authentication service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )


def check_role_permissions(user_role: str, service: str, method: str, path: str) -> bool:
    """Check if user role has permission to access the service/endpoint."""

    try:
        role = UserRole(user_role)
    except ValueError:
        logger.warning(f"Invalid user role: {user_role}")
        return False

    permissions = ROLE_PERMISSIONS.get(role)
    if not permissions:
        return False

    # Check if admin (full access)
    if role == UserRole.ADMIN:
        return True

    # Check allowed services
    allowed_services = permissions.get("allowed_services", [])
    if "*" not in allowed_services and service not in allowed_services:
        return False

    # Check allowed methods
    allowed_methods = permissions.get("allowed_methods", [])
    if "*" not in allowed_methods and method not in allowed_methods:
        return False

    # Check restricted endpoints
    restricted_endpoints = permissions.get("restricted_endpoints", [])
    for restricted in restricted_endpoints:
        if path.startswith(restricted):
            return False

    return True


async def log_security_event(event_type: str, user_id: str, details: dict, request: Request):
    """Log security events for monitoring and auditing."""

    security_event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent", ""),
        "path": str(request.url.path),
        "method": request.method,
        "details": details
    }

    # Mask sensitive data in logs
    masked_event = data_masking.mask_sensitive_dict(security_event)

    if event_type in ["authentication_failure", "authorization_failure", "suspicious_activity"]:
        logger.warning(f"Security Event: {json.dumps(masked_event)}")
    else:
        logger.info(f"Security Event: {json.dumps(masked_event)}")


async def proxy_request(service: str, path: str, request: Request, user_data: Optional[dict] = None):
    """Proxy request to appropriate microservice with enhanced security."""

    if service not in SERVICE_URLS:
        await log_security_event(
            "invalid_service_access",
            user_data.get("user_id", "anonymous") if user_data else "anonymous",
            {"service": service, "available_services": list(SERVICE_URLS.keys())},
            request
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )

    # Check role-based permissions
    if user_data:
        user_role = user_data.get("role")
        if not check_role_permissions(user_role, service, request.method, path):
            await log_security_event(
                "authorization_failure",
                user_data["user_id"],
                {
                    "service": service,
                    "method": request.method,
                    "path": path,
                    "role": user_role
                },
                request
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access this resource"
            )

    url = f"{SERVICE_URLS[service]}{path}"

    # Prepare secure headers
    headers = {}

    # Copy safe headers only
    safe_headers = {
        "content-type", "accept", "accept-language", "accept-encoding",
        "user-agent", "x-requested-with", "x-forwarded-for", "x-real-ip"
    }

    for key, value in request.headers.items():
        if key.lower() in safe_headers:
            headers[key] = value

    # Add user context headers if authenticated
    if user_data:
        headers["X-User-ID"] = user_data["user_id"]
        headers["X-User-Role"] = user_data["role"]
        headers["X-User-Permissions"] = ",".join(user_data.get("permissions", []))
        headers["X-Request-ID"] = secrets.token_urlsafe(16)  # For request tracing

    # Add security headers
    headers["X-Gateway-Version"] = "1.0.0"
    headers["X-Request-Time"] = str(int(time.time()))

    # Get request body
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()

    try:
        timeout = httpx.Timeout(30.0, connect=5.0)  # 30s total, 5s connect

        async with httpx.AsyncClient(timeout=timeout) as client:
            # Log request for audit (mask sensitive data)
            if user_data:
                await log_security_event(
                    "api_request",
                    user_data["user_id"],
                    {
                        "service": service,
                        "method": request.method,
                        "path": path,
                        "body_size": len(body) if body else 0
                    },
                    request
                )

            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.query_params,
                content=body
            )

            # Filter response headers for security
            response_headers = {}
            safe_response_headers = {
                "content-type", "content-length", "cache-control",
                "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"
            }

            for key, value in response.headers.items():
                if key.lower() in safe_response_headers:
                    response_headers[key] = value

            # Add security headers to response
            response_headers.update(SecurityConfig.SECURITY_HEADERS)

            return JSONResponse(
                content=response.json() if response.content else {},
                status_code=response.status_code,
                headers=response_headers
            )

    except httpx.TimeoutException:
        logger.error(f"Timeout proxying request to {service}: {url}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Service request timeout"
        )
    except httpx.RequestError as e:
        logger.error(f"Error proxying request to {service}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error proxying request to {service}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Oxygen Supply Platform API Gateway",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "services": list(SERVICE_URLS.keys())
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    service_health = {}
    
    async with httpx.AsyncClient() as client:
        for service_name, service_url in SERVICE_URLS.items():
            try:
                response = await client.get(f"{service_url}/health", timeout=5.0)
                service_health[service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds()
                }
            except Exception:
                service_health[service_name] = {
                    "status": "unreachable",
                    "response_time": None
                }
    
    return {
        "gateway_status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": service_health
    }


# Authentication routes (no auth required)
@app.post("/auth/register")
async def register(request: Request):
    """User registration."""
    response = await proxy_request("user", "/auth/register", request)
    return response


@app.post("/auth/login")
async def login(request: Request):
    """User login."""
    response = await proxy_request("user", "/auth/login", request)
    return response


@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """Refresh access token."""
    response = await proxy_request("user", "/auth/refresh", request)
    return response


# Protected routes
@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def user_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to User Service."""
    response = await proxy_request("user", f"/{path}", request, user_data)
    return response


@app.api_route("/suppliers/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def supplier_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Supplier Onboarding Service."""
    response = await proxy_request("supplier_onboarding", f"/{path}", request, user_data)
    return response


@app.api_route("/locations", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def location_service_root(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Location Service root endpoint."""
    response = await proxy_request("location", "/locations", request, user_data)
    return response


@app.api_route("/locations/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def location_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Location Service."""
    response = await proxy_request("location", f"/{path}", request, user_data)
    return response


@app.api_route("/inventory/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def inventory_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Inventory Service."""
    response = await proxy_request("inventory", f"/{path}", request, user_data)
    return response


@app.api_route("/orders", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def order_service_root(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Order Service root endpoint."""
    response = await proxy_request("order", "/orders", request, user_data)
    return response


@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def order_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Order Service."""
    response = await proxy_request("order", f"/orders/{path}", request, user_data)
    return response


# Pricing Service Routes
@app.api_route("/pricing/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def pricing_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service - Price comparison and management."""
    response = await proxy_request("pricing", f"/api/v1/pricing/{path}", request, user_data)
    return response


@app.api_route("/vendors/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def vendors_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service - Vendor discovery and management."""
    response = await proxy_request("pricing", f"/api/v1/vendors/{path}", request, user_data)
    return response


@app.api_route("/products/catalog/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def product_catalog_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service - Product catalog browsing."""
    response = await proxy_request("pricing", f"/api/v1/products/catalog/{path}", request, user_data)
    return response


@app.api_route("/products/search", methods=["POST"])
async def product_search_service(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service - Advanced product search."""
    response = await proxy_request("pricing", "/api/v1/products/search", request, user_data)
    return response


@app.api_route("/products/availability/check", methods=["POST"])
async def product_availability_service(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service - Product availability checking."""
    response = await proxy_request("pricing", "/api/v1/products/availability/check", request, user_data)
    return response


# Product Catalog Routes (Inventory Service)
@app.api_route("/catalog/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catalog_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Inventory Service Product Catalog."""
    response = await proxy_request("inventory", f"/catalog/{path}", request, user_data)
    return response


# Direct Ordering Routes (Order Service)
@app.api_route("/orders/direct", methods=["POST"])
async def direct_order_service(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Order Service Direct Ordering."""
    response = await proxy_request("order", "/orders/direct", request, user_data)
    return response


@app.api_route("/orders/pricing", methods=["POST"])
async def order_pricing_service(request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Order Service Pricing."""
    response = await proxy_request("order", "/orders/pricing", request, user_data)
    return response


@app.api_route("/delivery/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def delivery_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Delivery Service."""
    response = await proxy_request("delivery", f"/{path}", request, user_data)
    return response


@app.api_route("/payments/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def payment_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Payment Service."""
    response = await proxy_request("payment", f"/payments/{path}", request, user_data)
    return response


@app.api_route("/reviews/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def review_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Review Service."""
    response = await proxy_request("review", f"/{path}", request, user_data)
    return response


@app.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def notification_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Notification Service."""
    response = await proxy_request("notification", f"/{path}", request, user_data)
    return response


@app.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def admin_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Admin Service."""
    # Check if user has admin role
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    response = await proxy_request("admin", f"/{path}", request, user_data)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
