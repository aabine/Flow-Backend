from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
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

from app.api.dashboard import router as dashboard_router
from app.api.admin_management import router as admin_management_router
from app.api.analytics import router as analytics_router
from app.core.config import get_settings
from app.core.database import init_db
from app.services.event_listener_service import event_listener
from app.services.system_monitoring_service import SystemMonitoringService

settings = get_settings()
monitoring_service = SystemMonitoringService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Starting Admin Service...")

    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")

        # Start event listener service (graceful startup)
        try:
            await event_listener.start_listening()
            logger.info("✅ Event listener service started")
        except Exception as e:
            logger.warning(f"⚠️ Event listener startup warning: {e}")
            logger.info("📝 Admin service will continue without RabbitMQ")

        # Start background tasks
        asyncio.create_task(metrics_collection_task())
        logger.info("✅ Background tasks started")

        logger.info("🎉 Admin Service startup completed successfully!")

    except Exception as e:
        logger.error(f"❌ Critical error during Admin Service startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("🛑 Shutting down Admin Service...")
    try:
        await event_listener.stop_listening()
        logger.info("✅ Event listener stopped")
    except Exception as e:
        logger.warning(f"⚠️ Error stopping event listener: {e}")

    logger.info("👋 Admin Service shutdown completed")


async def metrics_collection_task():
    """Background task to collect system metrics periodically."""
    from app.core.database import AsyncSessionLocal
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await monitoring_service.collect_system_metrics(db)
            
            # Wait 5 minutes before next collection
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"Error in metrics collection task: {e}")
            # Wait 1 minute before retrying
            await asyncio.sleep(60)


app = FastAPI(
    title="Admin Service",
    description="Comprehensive administrative service for the Oxygen Supply Platform",
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
app.include_router(dashboard_router, prefix="/admin/dashboard", tags=["dashboard"])
app.include_router(admin_management_router, prefix="/admin", tags=["admin-management"])
app.include_router(analytics_router, prefix="/admin/analytics", tags=["analytics"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Admin Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "description": "Comprehensive administrative service for the Oxygen Supply Platform"
    }


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint with dependency status."""

    # Get RabbitMQ connection status
    rabbitmq_status = event_listener.get_connection_status()

    # Determine overall health
    is_healthy = True
    issues = []

    if not rabbitmq_status["connected"]:
        issues.append("RabbitMQ connection unavailable")
        # Note: We don't mark as unhealthy since service can run without RabbitMQ

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "Admin Service",
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


@app.get("/admin/status")
async def admin_status():
    """Admin service status with detailed information."""
    from app.core.database import AsyncSessionLocal
    
    try:
        async with AsyncSessionLocal() as db:
            system_health = await monitoring_service.get_system_health(db)
            system_overview = await monitoring_service.get_system_overview(db)
        
        return {
            "service": "Admin Service",
            "status": "operational",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "system_health": system_health.dict(),
            "system_overview": system_overview,
            "features": [
                "Dashboard Analytics",
                "User Management", 
                "Order Management",
                "Review Moderation",
                "System Monitoring",
                "Financial Analytics",
                "Real-time Alerts",
                "Audit Logging"
            ]
        }
    except Exception as e:
        return {
            "service": "Admin Service",
            "status": "degraded",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.ADMIN_SERVICE_PORT,
        reload=settings.DEBUG
    )
