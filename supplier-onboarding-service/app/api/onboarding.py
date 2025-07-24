from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.schemas.onboarding import SupplierKYC, SupplierKYCResponse, SupplierStatusUpdate
from app.schemas.document import DocumentUploadResponse
from app.services.onboarding_service import OnboardingService
from app.services.document_service import DocumentService
from app.core.database import get_db

router = APIRouter(prefix="/onboarding", tags=["Supplier Onboarding"])

@router.post("/kyc", response_model=SupplierKYCResponse)
async def submit_kyc(
    kyc_data: SupplierKYC,
    db: AsyncSession = Depends(get_db)
):
    return await OnboardingService().submit_kyc(db, kyc_data)

@router.post("/documents", response_model=List[DocumentUploadResponse])
async def upload_documents(
    supplier_id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    return await DocumentService().upload_documents(db, supplier_id, files)

@router.get("/status/{supplier_id}", response_model=SupplierKYCResponse)
async def get_onboarding_status(
    supplier_id: str,
    db: AsyncSession = Depends(get_db)
):
    return await OnboardingService().get_status(db, supplier_id)

@router.post("/review/{supplier_id}", response_model=SupplierKYCResponse)
async def review_supplier(
    supplier_id: str,
    status_update: SupplierStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    return await OnboardingService().review_supplier(db, supplier_id, status_update) 