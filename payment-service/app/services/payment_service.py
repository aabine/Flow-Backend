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
        import uuid
        payment_uuid = uuid.UUID(payment_id) if isinstance(payment_id, str) else payment_id
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_uuid)
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
        import uuid
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        query = select(Payment).where(Payment.user_id == user_uuid)
        
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

    async def get_payment_by_id(self, payment_id: str) -> Optional[Payment]:
        """Get payment by ID (alias for get_payment)."""
        return await self.get_payment(payment_id)

    async def can_access_payment(self, payment: Payment, user_id: str, role: str) -> bool:
        """Check if user can access payment."""
        if role == "admin":
            return True
        return payment.user_id == user_id or payment.vendor_id == user_id

    async def update_payment_with_paystack_data(self, payment_id: str, paystack_data: dict):
        """Update payment with Paystack data."""
        payment = await self.get_payment(payment_id)
        if payment:
            payment.paystack_reference = paystack_data.get("reference")
            payment.paystack_access_code = paystack_data.get("access_code")
            payment.authorization_url = paystack_data.get("authorization_url")
            await self.db.commit()

    async def process_split_payments(self, payment_id: str):
        """Process split payments (placeholder)."""
        # Implementation would handle actual payment splitting
        pass

    async def log_webhook(self, webhook_data: dict):
        """Log webhook data (placeholder)."""
        # Implementation would log webhook for audit
        pass

    async def handle_successful_payment(self, payment_data: dict):
        """Handle successful payment webhook (placeholder)."""
        pass

    async def handle_failed_payment(self, payment_data: dict):
        """Handle failed payment webhook (placeholder)."""
        pass

    async def handle_successful_transfer(self, transfer_data: dict):
        """Handle successful transfer webhook (placeholder)."""
        pass

    async def handle_failed_transfer(self, transfer_data: dict):
        """Handle failed transfer webhook (placeholder)."""
        pass

    async def can_access_payment_splits(self, payment: Payment, user_id: str, role: str) -> bool:
        """Check if user can access payment splits."""
        return await self.can_access_payment(payment, user_id, role)

    async def get_payment_splits(self, payment_id: str) -> List:
        """Get payment splits (placeholder)."""
        return []

    async def update_payment_status_to_refunded(self, payment_id: str, refund_result: dict, reason: str):
        """Update payment status to refunded (placeholder)."""
        await self.update_payment_status(payment_id, PaymentStatus.REFUNDED)

    async def get_vendor_earnings(self, vendor_id: str, start_date=None, end_date=None) -> dict:
        """Get vendor earnings (placeholder)."""
        return {"total_earnings": 0, "payment_count": 0}

    async def get_platform_revenue(self, start_date=None, end_date=None) -> dict:
        """Get platform revenue (placeholder)."""
        return {"total_revenue": 0, "payment_count": 0}
