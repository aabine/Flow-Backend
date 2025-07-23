from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import os
from typing import Optional
import json
from datetime import datetime

app = FastAPI(
    title="Oxygen Supply Platform API Gateway",
    description="Central API Gateway for the Oxygen Supply Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Service URLs from environment
SERVICE_URLS = {
    "user": os.getenv("USER_SERVICE_URL", "http://localhost:8001"),
    "supplier_onboarding": os.getenv("SUPPLIER_ONBOARDING_SERVICE_URL", "http://localhost:8002"),
    "location": os.getenv("LOCATION_SERVICE_URL", "http://localhost:8003"),
    "inventory": os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8004"),
    "order": os.getenv("ORDER_SERVICE_URL", "http://localhost:8005"),
    "pricing": os.getenv("PRICING_SERVICE_URL", "http://localhost:8006"),
    "delivery": os.getenv("DELIVERY_SERVICE_URL", "http://localhost:8007"),
    "payment": os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8008"),
    "review": os.getenv("REVIEW_SERVICE_URL", "http://localhost:8009"),
    "notification": os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010"),
    "admin": os.getenv("ADMIN_SERVICE_URL", "http://localhost:8011"),
}


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token with User Service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVICE_URLS['user']}/auth/verify-token",
                headers={"Authorization": f"Bearer {credentials.credentials}"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Token verification failed")


async def proxy_request(service: str, path: str, request: Request, user_data: Optional[dict] = None):
    """Proxy request to appropriate microservice."""
    if service not in SERVICE_URLS:
        raise HTTPException(status_code=404, detail="Service not found")
    
    url = f"{SERVICE_URLS[service]}{path}"
    
    # Prepare headers
    headers = dict(request.headers)
    if user_data:
        headers["X-User-ID"] = user_data.get("user_id", "")
        headers["X-User-Role"] = user_data.get("role", "")
    
    # Get request body
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            return response
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")


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
    return response.json()


@app.post("/auth/login")
async def login(request: Request):
    """User login."""
    response = await proxy_request("user", "/auth/login", request)
    return response.json()


@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """Refresh access token."""
    response = await proxy_request("user", "/auth/refresh", request)
    return response.json()


# Protected routes
@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def user_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to User Service."""
    response = await proxy_request("user", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/suppliers/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def supplier_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Supplier Onboarding Service."""
    response = await proxy_request("supplier_onboarding", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/locations/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def location_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Location Service."""
    response = await proxy_request("location", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/inventory/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def inventory_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Inventory Service."""
    response = await proxy_request("inventory", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def order_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Order Service."""
    response = await proxy_request("order", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/pricing/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def pricing_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Pricing Service."""
    response = await proxy_request("pricing", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/delivery/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def delivery_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Delivery Service."""
    response = await proxy_request("delivery", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/payments/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def payment_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Payment Service."""
    response = await proxy_request("payment", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/reviews/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def review_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Review Service."""
    response = await proxy_request("review", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def notification_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Notification Service."""
    response = await proxy_request("notification", f"/{path}", request, user_data)
    return response.json()


@app.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def admin_service(path: str, request: Request, user_data: dict = Depends(verify_token)):
    """Proxy to Admin Service."""
    # Check if user has admin role
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    response = await proxy_request("admin", f"/{path}", request, user_data)
    return response.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
