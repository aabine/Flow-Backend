from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.reviews import router as reviews_router
from app.core.config import get_settings
from app.core.database import init_db
from app.services.event_service import event_service

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Review Service...")

    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")

        # Start event service (graceful startup)
        try:
            await event_service.connect()
            logger.info("✅ Event service started")
        except Exception as e:
            logger.warning(f"⚠️ Event service startup warning: {e}")
            logger.info("📝 Review service will continue without RabbitMQ")

        logger.info("🎉 Review Service startup completed successfully!")

    except Exception as e:
        logger.error(f"❌ Critical error during Review Service startup: {e}")
        raise
    
    yield

    # Shutdown
    logger.info("🛑 Shutting down Review Service...")
    try:
        await event_service.disconnect()
        logger.info("✅ Event service stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping event service: {e}")

    logger.info("👋 Review Service shutdown completed")


app = FastAPI(
    title="Review Service",
    description="Rating and feedback system for the Oxygen Supply Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(reviews_router, prefix="/reviews", tags=["reviews"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Review Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "description": "Rating and feedback system for the Oxygen Supply Platform"
    }


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint with dependency status."""

    # Get RabbitMQ connection status
    rabbitmq_status = event_service.get_connection_status()

    # Determine overall health
    is_healthy = True
    issues = []

    if not rabbitmq_status["connected"]:
        issues.append("RabbitMQ connection unavailable")
        # Note: We don't mark as unhealthy since service can run without RabbitMQ

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "Review Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "rabbitmq": {
                "status": rabbitmq_status["state"],
                "connected": rabbitmq_status["connected"],
                "pending_events": rabbitmq_status["pending_events"],
                "url": rabbitmq_status["rabbitmq_url"]
            }
        },
        "issues": issues
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.REVIEW_SERVICE_PORT,
        reload=settings.DEBUG
    )
