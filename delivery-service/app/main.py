from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import get_settings
from app.core.database import init_db, close_db, check_db_health
from app.core.db_init import init_delivery_database
from app.api import deliveries, drivers, routes
from app.services.event_service import event_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 Starting Delivery Service...")
    try:
        # Initialize database with per-service initialization
        db_success = await init_delivery_database()
        if db_success:
            logger.info("✅ Database initialization completed")
        else:
            logger.error("❌ Database initialization failed")
            # Don't exit - let the service start but log the error

        # Start event service (graceful startup)
        try:
            await event_service.connect()
            logger.info("✅ Event service started")
        except Exception as e:
            logger.warning(f"⚠️ Event service startup warning: {e}")
            logger.info("📝 Delivery service will continue without RabbitMQ")

        logger.info("🎉 Delivery Service startup completed successfully!")
    except Exception as e:
        logger.error(f"❌ Critical error during Delivery Service startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("🛑 Shutting down Delivery Service...")
    try:
        await event_service.disconnect()
        logger.info("✅ Event service stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping event service: {e}")

    await close_db()
    logger.info("👋 Delivery Service shutdown completed")


# Create FastAPI app
app = FastAPI(
    title="Delivery Service",
    description="Microservice for managing oxygen delivery operations",
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


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "error": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )


# Health check endpoints
@app.get("/health")
async def health_check():
    """Enhanced health check endpoint with dependency status."""
    try:
        db_healthy = await check_db_health()

        # Get RabbitMQ connection status
        rabbitmq_status = event_service.get_connection_status()

        # Determine overall health
        is_healthy = db_healthy
        issues = []

        if not db_healthy:
            issues.append("Database connection unavailable")

        if not rabbitmq_status["connected"]:
            issues.append("RabbitMQ connection unavailable")
            # Note: We don't mark as unhealthy since service can run without RabbitMQ

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "service": "Delivery Service",
            "version": settings.VERSION,
            "dependencies": {
                "database": "connected" if db_healthy else "disconnected",
                "rabbitmq": {
                    "status": rabbitmq_status["state"],
                    "connected": rabbitmq_status["connected"],
                    "pending_events": rabbitmq_status["pending_events"],
                    "url": rabbitmq_status["rabbitmq_url"]
                }
            },
            "issues": issues
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "Delivery Service",
                "version": settings.VERSION,
                "error": str(e)
            }
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "delivery-service",
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "deliveries": "/api/v1/deliveries",
            "drivers": "/api/v1/drivers",
            "routes": "/api/v1/routes"
        }
    }

@app.get("/deliveries")
async def deliveries_info():
    """Deliveries endpoint information."""
    return {
        "message": "Delivery Service - Deliveries API",
        "endpoints": {
            "GET /api/v1/deliveries": "Get deliveries with filtering (requires authentication)",
            "POST /api/v1/deliveries": "Create a new delivery (requires authentication)",
            "GET /api/v1/deliveries/{delivery_id}": "Get specific delivery (requires authentication)",
            "PUT /api/v1/deliveries/{delivery_id}": "Update delivery (requires authentication)"
        },
        "authentication": "Required for all endpoints except this one",
        "documentation": "/docs"
    }


# Include API routers
app.include_router(
    deliveries.router,
    prefix="/api/v1/deliveries",
    tags=["deliveries"]
)

app.include_router(
    drivers.router,
    prefix="/api/v1/drivers",
    tags=["drivers"]
)

app.include_router(
    routes.router,
    prefix="/api/v1/routes",
    tags=["routes"]
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8007,
        reload=settings.DEBUG
    )
