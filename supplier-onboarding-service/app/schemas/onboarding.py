from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from shared.models import SupplierStatus

class SupplierKYC(BaseModel):
    user_id: str
    business_name: str
    registration_number: Optional[str] = None
    tax_identification_number: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    business_address: Optional[str] = None

class SupplierKYCResponse(SupplierKYC):
    id: str
    status: SupplierStatus
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class SupplierStatusUpdate(BaseModel):
    status: SupplierStatus
    rejection_reason: Optional[str] = None 