from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import get_db
from app.api.inventory import router as inventory_router
from app.api.stock_movements import router as stock_movements_router
from app.services.event_service import event_service
from shared.models import APIResponse

app = FastAPI(
    title="Inventory Service",
    description="Oxygen cylinder inventory management service",
    version="1.0.0"
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


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    await event_service.connect()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await event_service.disconnect()

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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
