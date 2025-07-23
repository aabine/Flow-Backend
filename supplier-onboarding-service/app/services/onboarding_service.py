from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.supplier import Supplier
from app.schemas.onboarding import SupplierKYC, SupplierStatusUpdate
from shared.models import SupplierStatus
from datetime import datetime
import uuid

class OnboardingService:
    async def submit_kyc(self, db: AsyncSession, kyc_data: SupplierKYC):
        supplier = Supplier(
            id=uuid.uuid4(),
            user_id=uuid.UUID(kyc_data.user_id),
            business_name=kyc_data.business_name,
            registration_number=kyc_data.registration_number,
            tax_identification_number=kyc_data.tax_identification_number,
            contact_person=kyc_data.contact_person,
            contact_phone=kyc_data.contact_phone,
            business_address=kyc_data.business_address,
            status=SupplierStatus.PENDING_VERIFICATION
        )
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)
        return supplier

    async def get_status(self, db: AsyncSession, supplier_id: str):
        result = await db.execute(select(Supplier).where(Supplier.id == uuid.UUID(supplier_id)))
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise Exception("Supplier not found")
        return supplier

    async def review_supplier(self, db: AsyncSession, supplier_id: str, status_update: SupplierStatusUpdate):
        result = await db.execute(select(Supplier).where(Supplier.id == uuid.UUID(supplier_id)))
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise Exception("Supplier not found")
        supplier.status = status_update.status
        supplier.rejection_reason = status_update.rejection_reason
        supplier.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(supplier)
        return supplier 