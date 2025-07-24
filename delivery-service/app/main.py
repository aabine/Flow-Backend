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
from app.api import deliveries, drivers, routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Delivery Service...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Delivery Service...")
    await close_db()


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
    """Health check endpoint."""
    try:
        db_healthy = await check_db_health()
        
        return {
            "status": "healthy" if db_healthy else "unhealthy",
            "service": "delivery-service",
            "version": settings.VERSION,
            "database": "connected" if db_healthy else "disconnected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "delivery-service",
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
        "docs": "/docs"
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
