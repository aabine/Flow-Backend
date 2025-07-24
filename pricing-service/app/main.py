from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.api.pricing import router as pricing_router
from app.core.config import get_settings
from app.core.database import init_db, close_db
from shared.models import APIResponse

settings = get_settings()

app = FastAPI(
    title="Pricing Service",
    description="Competitive bidding and quote management system for oxygen supply platform",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(pricing_router, tags=["pricing"])


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    await init_db()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await close_db()


@app.get("/", response_model=APIResponse)
async def root():
    """Root endpoint."""
    return APIResponse(
        success=True,
        message="Pricing Service API",
        data={
            "service": "pricing-service",
            "version": settings.VERSION,
            "description": "Competitive bidding and quote management system"
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "pricing-service",
        "version": settings.VERSION,
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)