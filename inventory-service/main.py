from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import get_db
from app.api.inventory import router as inventory_router
from app.api.stock_movements import router as stock_movements_router
from app.services.event_service import event_service
from shared.models import APIResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Inventory Service...")

    try:
        # Start event service (graceful startup)
        try:
            await event_service.connect()
            logger.info("✅ Event service started")
        except Exception as e:
            logger.warning(f"⚠️ Event service startup warning: {e}")
            logger.info("📝 Inventory service will continue without RabbitMQ")

        logger.info("🎉 Inventory Service startup completed successfully!")

    except Exception as e:
        logger.error(f"❌ Critical error during Inventory Service startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("🛑 Shutting down Inventory Service...")
    try:
        await event_service.disconnect()
        logger.info("✅ Event service stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping event service: {e}")

    logger.info("👋 Inventory Service shutdown completed")


app = FastAPI(
    title="Inventory Service",
    description="Oxygen cylinder inventory management service",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(inventory_router, prefix="/inventory", tags=["inventory"])
app.include_router(stock_movements_router, prefix="/stock-movements", tags=["stock-movements"])




@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Inventory Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
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
        "service": "Inventory Service",
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
    uvicorn.run(app, host="0.0.0.0", port=8004)
