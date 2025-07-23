from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.onboarding import router as onboarding_router

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

app.include_router(onboarding_router)

@app.get("/")
async def root():
    return {"service": "Supplier Onboarding Service", "version": "1.0.0"} 