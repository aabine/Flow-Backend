from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, List
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.payment import Payment, PaymentSplit
from app.schemas.payment import PaymentCreate, PaymentResponse
from shared.models import PaymentStatus


class PaymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_payment(self, payment_data: PaymentCreate, user_id: str, vendor_id: str, platform_fee_percentage: float) -> Payment:
        """Create a new payment record."""
        platform_fee = payment_data.amount * (platform_fee_percentage / 100)
        vendor_amount = payment_data.amount - platform_fee
        
        payment = Payment(
            id=str(uuid.uuid4()),
            order_id=payment_data.order_id,
            user_id=user_id,
            vendor_id=vendor_id,
            amount=payment_data.amount,
            platform_fee=platform_fee,
            vendor_amount=vendor_amount,
            currency=payment_data.currency,
            status=PaymentStatus.PENDING
        )
        
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        
        # Create payment splits
        await self._create_payment_splits(payment)
        
        return payment

    async def _create_payment_splits(self, payment: Payment):
        """Create payment splits for vendor and platform."""
        # Vendor split
        vendor_split = PaymentSplit(
            id=str(uuid.uuid4()),
            payment_id=payment.id,
            recipient_type="vendor",
            recipient_id=payment.vendor_id,
            amount=payment.vendor_amount,
            percentage=((payment.vendor_amount / payment.amount) * 100)
        )
        
        # Platform split
        platform_split = PaymentSplit(
            id=str(uuid.uuid4()),
            payment_id=payment.id,
            recipient_type="platform",
            recipient_id="platform",
            amount=payment.platform_fee,
            percentage=((payment.platform_fee / payment.amount) * 100)
        )
        
        self.db.add(vendor_split)
        self.db.add(platform_split)
        await self.db.commit()

    async def get_payment(self, payment_id: str) -> Optional[Payment]:
        """Get payment by ID."""
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalar_one_or_none()

    async def get_payment_by_reference(self, reference: str) -> Optional[Payment]:
        """Get payment by Paystack reference."""
        result = await self.db.execute(
            select(Payment).where(Payment.paystack_reference == reference)
        )
        return result.scalar_one_or_none()

    async def update_payment_status(self, payment_id: str, status: PaymentStatus, **kwargs) -> Optional[Payment]:
        """Update payment status and other fields."""
        payment = await self.get_payment(payment_id)
        if not payment:
            return None
        
        payment.status = status
        
        # Update additional fields if provided
        for key, value in kwargs.items():
            if hasattr(payment, key):
                setattr(payment, key, value)
        
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def get_user_payments(self, user_id: str, page: int = 1, size: int = 20, status_filter: Optional[PaymentStatus] = None) -> tuple[List[Payment], int]:
        """Get payments for a user with pagination."""
        query = select(Payment).where(Payment.user_id == user_id)
        
        if status_filter:
            query = query.where(Payment.status == status_filter)
        
        # Count total
        count_result = await self.db.execute(query)
        total = len(count_result.all())
        
        # Get paginated results
        query = query.offset((page - 1) * size).limit(size).order_by(Payment.created_at.desc())
        result = await self.db.execute(query)
        payments = result.scalars().all()
        
        return list(payments), total

    async def get_vendor_payments(self, vendor_id: str, page: int = 1, size: int = 20) -> tuple[List[Payment], int]:
        """Get payments for a vendor with pagination."""
        query = select(Payment).where(Payment.vendor_id == vendor_id)
        
        # Count total
        count_result = await self.db.execute(query)
        total = len(count_result.all())
        
        # Get paginated results
        query = query.offset((page - 1) * size).limit(size).order_by(Payment.created_at.desc())
        result = await self.db.execute(query)
        payments = result.scalars().all()
        
        return list(payments), total
