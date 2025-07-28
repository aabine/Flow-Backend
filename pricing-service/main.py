from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import init_db, close_db, check_db_health
from app.api import vendors, products, pricing
from app.services.event_service import event_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Pricing Service...")
    
    # Initialize database
    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    # Check database health
    try:
        await check_db_health()
        logger.info("✅ Database health check passed")
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        raise
    
    # Initialize event service
    try:
        await event_service.connect()
        logger.info("✅ Event service connected")
    except Exception as e:
        logger.warning(f"⚠️ Event service connection failed: {e}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Pricing Service...")
    try:
        await event_service.disconnect()
        logger.info("✅ Event service stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping event service: {e}")

    await close_db()
    logger.info("👋 Pricing Service shutdown completed")


# Create FastAPI app
app = FastAPI(
    title="Pricing Service",
    description="Microservice for managing product pricing, vendor catalogs, and price comparison",
    version=settings.VERSION,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled error in {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        db_healthy = await check_db_health()
        return {
            "status": "healthy" if db_healthy else "unhealthy",
            "service": "pricing-service",
            "version": settings.VERSION,
            "database": "connected" if db_healthy else "disconnected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "pricing-service",
                "version": settings.VERSION,
                "error": str(e)
            }
        )


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Pricing Service",
        "version": settings.VERSION,
        "description": "Product pricing, vendor catalogs, and price comparison",
        "endpoints": {
            "vendors": "/api/v1/vendors",
            "products": "/api/v1/products", 
            "pricing": "/api/v1/pricing",
            "health": "/health",
            "docs": "/docs"
        },
        "features": [
            "Vendor discovery and management",
            "Product catalog browsing",
            "Multi-vendor price comparison",
            "Real-time pricing updates",
            "Geographical vendor filtering",
            "Direct order pricing"
        ]
    }


# Include API routers
app.include_router(
    vendors.router,
    prefix="/api/v1/vendors",
    tags=["vendors"]
)

app.include_router(
    products.router,
    prefix="/api/v1/products",
    tags=["products"]
)

app.include_router(
    pricing.router,
    prefix="/api/v1/pricing",
    tags=["pricing"]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )
