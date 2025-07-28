from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.onboarding import router as onboarding_router
from app.core.db_init import init_supplier_onboarding_database
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Supplier Onboarding Service",
    description="KYC and document verification for suppliers",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization flag
_db_initialized = False

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    global _db_initialized
    if not _db_initialized:
        logger.info("🚀 Starting Supplier Onboarding Service...")
        success = await init_supplier_onboarding_database()
        if success:
            logger.info("✅ Supplier Onboarding Service database initialization completed")
            _db_initialized = True
        else:
            logger.error("❌ Supplier Onboarding Service database initialization failed")
            # Don't exit - let the service start but log the error
    else:
        logger.info("ℹ️ Database already initialized")

app.include_router(onboarding_router)

@app.get("/")
async def root():
    return {
        "service": "Supplier Onboarding Service",
        "version": app.version,
        "description": "KYC and document verification for suppliers",
        "endpoints": {
            "applications": "/applications",
            "documents": "/documents",
            "verification": "/verification"
        }
    }

@app.get("/applications")
async def applications_info():
    """Applications endpoint information."""
    return {
        "message": "Supplier Onboarding - Applications API",
        "endpoints": {
            "GET /applications": "Get supplier applications (requires authentication)",
            "POST /applications": "Submit new supplier application (requires authentication)",
            "GET /applications/{application_id}": "Get specific application (requires authentication)",
            "PUT /applications/{application_id}": "Update application (requires authentication)"
        },
        "authentication": "Required for all endpoints except this one",
        "documentation": "/docs"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": app.title,
        "version": app.version,
        "timestamp": datetime.now().isoformat()
    }