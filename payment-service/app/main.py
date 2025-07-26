from fastapi import FastAPI, HTTPException, Depends, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List, Any
import os
import sys
import hmac
import hashlib
from contextlib import asynccontextmanager


from app.core.config import get_settings
from app.core.database import get_db
from app.models.payment import Payment, PaymentSplit, PaymentWebhook
from app.schemas.payment import (
    PaymentCreate, PaymentResponse, PaymentInitializeResponse,
    PaymentWebhookData, PaymentSplitResponse
)
from app.services.payment_service import PaymentService
from app.services.paystack_service import PaystackService
from app.services.event_service import EventService
from shared.models import PaymentStatus, UserRole, APIResponse

# Services will be initialized in the FastAPI lifespan
payment_service: Optional[PaymentService] = None
paystack_service = PaystackService()
event_service = EventService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_gen = get_db()
    db = await anext(db_gen)
    global payment_service
    payment_service = PaymentService(db)
    yield
    # Shutdown
    await db.close()

app = FastAPI(
    title="Payment Service",
    description="Payment processing and split payment service",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required"
        )
    return {"user_id": x_user_id, "role": x_user_role}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Payment Service",
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


@app.post("/payments/initialize", response_model=PaymentInitializeResponse)
async def initialize_payment(
    payment_data: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initialize payment with Paystack."""
    try:
        # Only hospitals can make payments
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can make payments"
            )
        
        # Create payment record
        payment = await payment_service.create_payment(
            payment_data, current_user["user_id"], "vendor_id_placeholder", 5.0
        )
        
        # Initialize payment with Paystack
        paystack_response = await paystack_service.initialize_payment(
            email=current_user.get("email", ""),
            amount=payment_data.amount,
            reference=payment.reference,
            callback_url=f"{get_settings().FRONTEND_URL}/payment/callback"
        )
        
        # Update payment with Paystack data
        await payment_service.update_payment_with_paystack_data(
            payment.id, paystack_response
        )
        
        return PaymentInitializeResponse(
            payment_id=str(payment.id),
            reference=payment.reference,
            authorization_url=paystack_response["authorization_url"],
            access_code=paystack_response["access_code"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize payment: {str(e)}"
        )


@app.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment details."""
    try:
        payment = await payment_service.get_payment(payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        # Check access permissions
        if not await payment_service.can_access_payment(payment, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return PaymentResponse.from_orm(payment)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get payment: {str(e)}"
        )


@app.get("/payments")
async def get_payments(
    page: int = 1,
    size: int = 20,
    status_filter: Optional[PaymentStatus] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payments for current user."""
    try:
        payments, total = await payment_service.get_user_payments(
            current_user["user_id"], page, size, status_filter
        )
        
        return {
            "payments": [PaymentResponse.from_orm(payment) for payment in payments],
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get payments: {str(e)}"
        )


@app.post("/payments/{payment_id}/verify", response_model=APIResponse)
async def verify_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify payment status with Paystack."""
    try:
        payment = await payment_service.get_payment(payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        # Check access permissions
        if not await payment_service.can_access_payment(payment, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Verify with Paystack
        verification_result = await paystack_service.verify_payment(payment.reference)
        
        # Update payment status
        updated_payment = await payment_service.update_payment_status(
            payment_id, PaymentStatus.COMPLETED
        )

        # If payment successful, process split payments
        if updated_payment and updated_payment.status == PaymentStatus.COMPLETED:
            await payment_service.process_split_payments(payment_id)
            await event_service.emit_payment_completed(updated_payment)
        
        return APIResponse(
            success=True,
            message="Payment verification completed",
            data={
                "payment_id": payment_id,
                "status": updated_payment.status,
                "amount": updated_payment.amount
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify payment: {str(e)}"
        )


@app.post("/webhooks/paystack")
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Paystack webhook events."""
    try:
        # Get raw body
        body = await request.body()
        
        # Verify webhook signature
        signature = request.headers.get("x-paystack-signature")
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")
        
        # Verify signature
        expected_signature = hmac.new(
            get_settings().PAYSTACK_SECRET_KEY.encode(),
            body,
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Parse webhook data
        webhook_data = await request.json()
        
        # Log webhook
        await payment_service.log_webhook(webhook_data)

        # Process webhook based on event type
        event_type = webhook_data.get("event")

        if event_type == "charge.success":
            await payment_service.handle_successful_payment(webhook_data["data"])
        elif event_type == "charge.failed":
            await payment_service.handle_failed_payment(webhook_data["data"])
        elif event_type == "transfer.success":
            await payment_service.handle_successful_transfer(webhook_data["data"])
        elif event_type == "transfer.failed":
            await payment_service.handle_failed_transfer(webhook_data["data"])
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


@app.get("/payments/{payment_id}/splits")
async def get_payment_splits(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment split details."""
    try:
        payment = await payment_service.get_payment(payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        # Check access permissions (admin or involved parties)
        if not await payment_service.can_access_payment_splits(payment, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        splits = await payment_service.get_payment_splits(payment_id)
        
        return {
            "payment_id": payment_id,
            "splits": [PaymentSplitResponse.from_orm(split) for split in splits],
            "total_splits": len(splits)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get payment splits: {str(e)}"
        )


@app.post("/payments/{payment_id}/refund", response_model=APIResponse)
async def refund_payment(
    payment_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Refund a payment (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        payment = await payment_service.get_payment(payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        if payment.status != PaymentStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed payments can be refunded"
            )
        
        # Process refund with Paystack
        refund_result = await paystack_service.refund_payment(
            payment.reference, payment.amount, reason
        )
        
        # Update payment status
        await payment_service.update_payment_status_to_refunded(
            payment_id, {}, reason
        )
        
        return APIResponse(
            success=True,
            message="Payment refunded successfully",
            data={
                "payment_id": payment_id,
                "refund_reference": refund_result.get("reference")
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refund payment: {str(e)}"
        )


@app.get("/vendors/{vendor_id}/earnings")
async def get_vendor_earnings(
    vendor_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor earnings summary."""
    try:
        # Check access permissions
        if current_user["role"] == UserRole.VENDOR and current_user["user_id"] != vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        elif current_user["role"] not in [UserRole.VENDOR, UserRole.ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        earnings = await payment_service.get_vendor_earnings(
            vendor_id, start_date, end_date
        )
        
        return earnings
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor earnings: {str(e)}"
        )


@app.get("/platform/revenue")
async def get_platform_revenue(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get platform revenue summary (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        revenue = await payment_service.get_platform_revenue(
            start_date, end_date
        )
        
        return revenue
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get platform revenue: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
