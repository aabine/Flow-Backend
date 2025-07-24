from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import sys
import os

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
    print("Starting Review Service...")
    
    # Initialize database
    await init_db()
    print("Database initialized")
    
    # Connect to RabbitMQ
    await event_service.connect()
    print("Connected to RabbitMQ")
    
    yield
    
    # Shutdown
    print("Shutting down Review Service...")
    await event_service.disconnect()
    print("Disconnected from RabbitMQ")


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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Review Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.REVIEW_SERVICE_PORT,
        reload=settings.DEBUG
    )
