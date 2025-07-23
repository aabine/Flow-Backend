from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import PaymentStatus


class PaymentCreate(BaseModel):
    order_id: str
    amount: float = Field(..., gt=0)
    currency: str = "NGN"
    callback_url: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    user_id: str
    vendor_id: str
    amount: float
    platform_fee: float
    vendor_amount: float
    currency: str
    status: PaymentStatus
    paystack_reference: Optional[str] = None
    payment_method: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentInitializeResponse(BaseModel):
    payment_id: str
    authorization_url: str
    access_code: str
    reference: str


class PaymentWebhookData(BaseModel):
    event: str
    data: dict


class PaymentSplitResponse(BaseModel):
    id: str
    payment_id: str
    recipient_type: str
    recipient_id: str
    amount: float
    percentage: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    page: int
    size: int
    pages: int


class PaymentVerificationResponse(BaseModel):
    payment_id: str
    status: PaymentStatus
    amount: float
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    reference: str
