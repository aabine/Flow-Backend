"""
PCI DSS compliant payment service with enhanced security features.
Implements secure Paystack integration, fraud detection, and transaction monitoring.
"""

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.security.auth import jwt_manager
from shared.security.encryption import encryption_manager, data_masking
from shared.security.api_security import SecureValidator
from app.models.payment import Payment, PaymentMethod, Transaction, FraudCheck, PaymentAudit
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PCICompliantPaymentService:
    """PCI DSS compliant payment service with enhanced security."""
    
    def __init__(self):
        self.paystack_secret_key = settings.PAYSTACK_SECRET_KEY
        self.paystack_public_key = settings.PAYSTACK_PUBLIC_KEY
        self.webhook_secret = settings.PAYSTACK_WEBHOOK_SECRET
        self.base_url = "https://api.paystack.co"
        
        # Fraud detection thresholds
        self.max_daily_amount = Decimal("1000000.00")  # 1M Naira
        self.max_transaction_amount = Decimal("500000.00")  # 500K Naira
        self.max_transactions_per_hour = 10
        self.suspicious_velocity_threshold = 5  # transactions in 5 minutes
        
        # PCI compliance settings
        self.enable_tokenization = True
        self.enable_encryption = True
        self.enable_audit_logging = True
        self.enable_fraud_detection = True
    
    async def initialize_payment(
        self,
        db: AsyncSession,
        amount: Decimal,
        currency: str,
        customer_email: str,
        order_id: str,
        user_id: str,
        metadata: Dict[str, Any] = None,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Initialize a secure payment with fraud detection."""
        
        # Validate inputs
        amount = SecureValidator.validate_decimal(amount, min_value=100.0, max_value=float(self.max_transaction_amount))
        customer_email = SecureValidator.validate_email(customer_email)
        
        # Fraud detection checks
        fraud_result = await self._perform_fraud_checks(
            db, user_id, amount, customer_email, ip_address
        )
        
        if fraud_result["is_suspicious"]:
            await self._log_security_event(
                "payment_fraud_detected",
                user_id,
                {
                    "amount": float(amount),
                    "email": data_masking.mask_email(customer_email),
                    "fraud_reasons": fraud_result["reasons"],
                    "ip_address": ip_address
                }
            )
            raise ValueError("Payment blocked due to security concerns")
        
        # Generate secure reference
        reference = self._generate_secure_reference(order_id)
        
        # Prepare payment data
        payment_data = {
            "amount": int(amount * 100),  # Convert to kobo
            "currency": currency.upper(),
            "email": customer_email,
            "reference": reference,
            "callback_url": f"{settings.FRONTEND_URL}/payment/callback",
            "metadata": {
                "order_id": order_id,
                "user_id": user_id,
                "platform": "oxygen_supply",
                **(metadata or {})
            }
        }
        
        try:
            # Initialize payment with Paystack
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    json=payment_data,
                    headers={
                        "Authorization": f"Bearer {self.paystack_secret_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise Exception(f"Paystack API error: {response.status_code}")
                
                result = response.json()
                
                if not result.get("status"):
                    raise Exception(f"Payment initialization failed: {result.get('message')}")
                
                # Store payment record
                payment = Payment(
                    reference=reference,
                    amount=amount,
                    currency=currency,
                    customer_email=encryption_manager.encrypt_field(customer_email, "email"),
                    order_id=order_id,
                    user_id=user_id,
                    status="pending",
                    paystack_access_code=result["data"]["access_code"],
                    created_at=datetime.utcnow(),
                    ip_address=ip_address
                )
                
                db.add(payment)
                await db.commit()
                await db.refresh(payment)
                
                # Log payment initialization
                await self._audit_payment_action(
                    db, payment.id, "initialized", user_id, ip_address,
                    {"amount": float(amount), "currency": currency}
                )
                
                return {
                    "status": "success",
                    "data": {
                        "authorization_url": result["data"]["authorization_url"],
                        "access_code": result["data"]["access_code"],
                        "reference": reference
                    }
                }
                
        except Exception as e:
            logger.error(f"Payment initialization error: {str(e)}")
            await self._log_security_event(
                "payment_initialization_failed",
                user_id,
                {
                    "error": str(e),
                    "amount": float(amount),
                    "email": data_masking.mask_email(customer_email)
                }
            )
            raise ValueError("Payment initialization failed")
    
    async def verify_payment(
        self,
        db: AsyncSession,
        reference: str,
        user_id: str = None,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Verify payment with enhanced security checks."""
        
        # Validate reference format
        if not self._validate_reference_format(reference):
            raise ValueError("Invalid payment reference format")
        
        try:
            # Get payment from database
            payment = await self._get_payment_by_reference(db, reference)
            if not payment:
                raise ValueError("Payment not found")
            
            # Verify with Paystack
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers={
                        "Authorization": f"Bearer {self.paystack_secret_key}"
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise Exception(f"Paystack verification error: {response.status_code}")
                
                result = response.json()
                
                if not result.get("status"):
                    raise Exception(f"Payment verification failed: {result.get('message')}")
                
                transaction_data = result["data"]
                
                # Validate transaction integrity
                if not self._validate_transaction_integrity(payment, transaction_data):
                    await self._log_security_event(
                        "payment_integrity_violation",
                        user_id,
                        {
                            "reference": reference,
                            "expected_amount": float(payment.amount),
                            "received_amount": transaction_data.get("amount", 0) / 100
                        }
                    )
                    raise ValueError("Payment integrity check failed")
                
                # Update payment status
                payment.status = transaction_data["status"]
                payment.gateway_response = json.dumps(transaction_data)
                payment.verified_at = datetime.utcnow()
                
                if transaction_data["status"] == "success":
                    payment.paid_at = datetime.utcnow()
                
                await db.commit()
                
                # Log verification
                await self._audit_payment_action(
                    db, payment.id, "verified", user_id, ip_address,
                    {"status": transaction_data["status"], "amount": float(payment.amount)}
                )
                
                return {
                    "status": "success",
                    "data": {
                        "reference": reference,
                        "amount": float(payment.amount),
                        "currency": payment.currency,
                        "status": payment.status,
                        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None
                    }
                }
                
        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
            await self._log_security_event(
                "payment_verification_failed",
                user_id,
                {"reference": reference, "error": str(e)}
            )
            raise ValueError("Payment verification failed")
    
    async def handle_webhook(
        self,
        db: AsyncSession,
        payload: bytes,
        signature: str,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Handle Paystack webhook with signature verification."""
        
        # Verify webhook signature
        if not self._verify_webhook_signature(payload, signature):
            await self._log_security_event(
                "webhook_signature_invalid",
                None,
                {"ip_address": ip_address, "signature": signature[:20] + "..."}
            )
            raise ValueError("Invalid webhook signature")
        
        try:
            # Parse webhook data
            webhook_data = json.loads(payload.decode("utf-8"))
            event_type = webhook_data.get("event")
            data = webhook_data.get("data", {})
            
            # Process based on event type
            if event_type == "charge.success":
                return await self._handle_successful_payment(db, data, ip_address)
            elif event_type == "charge.failed":
                return await self._handle_failed_payment(db, data, ip_address)
            elif event_type == "transfer.success":
                return await self._handle_successful_transfer(db, data, ip_address)
            else:
                logger.info(f"Unhandled webhook event: {event_type}")
                return {"status": "ignored", "event": event_type}
                
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            await self._log_security_event(
                "webhook_processing_failed",
                None,
                {"error": str(e), "ip_address": ip_address}
            )
            raise ValueError("Webhook processing failed")
    
    async def _perform_fraud_checks(
        self,
        db: AsyncSession,
        user_id: str,
        amount: Decimal,
        email: str,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Perform comprehensive fraud detection checks."""
        
        fraud_reasons = []
        risk_score = 0
        
        # Check 1: Amount limits
        if amount > self.max_transaction_amount:
            fraud_reasons.append("amount_exceeds_limit")
            risk_score += 50
        
        # Check 2: Daily transaction volume
        daily_total = await self._get_daily_transaction_total(db, user_id)
        if daily_total + amount > self.max_daily_amount:
            fraud_reasons.append("daily_limit_exceeded")
            risk_score += 40
        
        # Check 3: Transaction velocity
        recent_transactions = await self._get_recent_transaction_count(db, user_id, minutes=5)
        if recent_transactions >= self.suspicious_velocity_threshold:
            fraud_reasons.append("high_velocity")
            risk_score += 60
        
        # Check 4: IP address reputation (basic check)
        if ip_address and await self._is_suspicious_ip(db, ip_address):
            fraud_reasons.append("suspicious_ip")
            risk_score += 30
        
        # Check 5: Email domain validation
        if not self._validate_email_domain(email):
            fraud_reasons.append("suspicious_email_domain")
            risk_score += 20
        
        # Check 6: Time-based patterns
        if self._is_suspicious_time():
            fraud_reasons.append("suspicious_time")
            risk_score += 10
        
        # Store fraud check result
        fraud_check = FraudCheck(
            user_id=user_id,
            amount=amount,
            email=encryption_manager.encrypt_field(email, "email"),
            ip_address=ip_address,
            risk_score=risk_score,
            fraud_reasons=json.dumps(fraud_reasons),
            is_suspicious=risk_score >= 70,  # Threshold for blocking
            created_at=datetime.utcnow()
        )
        
        db.add(fraud_check)
        await db.commit()
        
        return {
            "is_suspicious": risk_score >= 70,
            "risk_score": risk_score,
            "reasons": fraud_reasons
        }

    def _generate_secure_reference(self, order_id: str) -> str:
        """Generate a secure payment reference."""
        timestamp = str(int(time.time()))
        random_part = secrets.token_urlsafe(8)
        return f"OXY_{timestamp}_{random_part}_{order_id[:8]}"

    def _validate_reference_format(self, reference: str) -> bool:
        """Validate payment reference format."""
        import re
        pattern = r'^OXY_\d+_[A-Za-z0-9_-]+_[A-Za-z0-9]+$'
        return bool(re.match(pattern, reference))

    def _verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature."""
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Webhook signature verification error: {str(e)}")
            return False

    def _validate_transaction_integrity(self, payment: Payment, transaction_data: Dict[str, Any]) -> bool:
        """Validate transaction data integrity."""
        try:
            # Check amount matches
            expected_amount = int(payment.amount * 100)  # Convert to kobo
            received_amount = transaction_data.get("amount", 0)

            if expected_amount != received_amount:
                return False

            # Check currency matches
            if payment.currency.upper() != transaction_data.get("currency", "").upper():
                return False

            # Check reference matches
            if payment.reference != transaction_data.get("reference", ""):
                return False

            return True

        except Exception as e:
            logger.error(f"Transaction integrity validation error: {str(e)}")
            return False

    async def _get_payment_by_reference(self, db: AsyncSession, reference: str) -> Optional[Payment]:
        """Get payment by reference."""
        result = await db.execute(
            select(Payment).where(Payment.reference == reference)
        )
        return result.scalar_one_or_none()

    async def _get_daily_transaction_total(self, db: AsyncSession, user_id: str) -> Decimal:
        """Get total transaction amount for user today."""
        today = datetime.utcnow().date()
        result = await db.execute(
            select(func.sum(Payment.amount)).where(
                and_(
                    Payment.user_id == user_id,
                    Payment.status == "success",
                    func.date(Payment.created_at) == today
                )
            )
        )
        total = result.scalar()
        return total or Decimal("0.00")

    async def _get_recent_transaction_count(self, db: AsyncSession, user_id: str, minutes: int = 5) -> int:
        """Get count of recent transactions for user."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        result = await db.execute(
            select(func.count(Payment.id)).where(
                and_(
                    Payment.user_id == user_id,
                    Payment.created_at >= cutoff_time
                )
            )
        )
        return result.scalar() or 0

    async def _is_suspicious_ip(self, db: AsyncSession, ip_address: str) -> bool:
        """Check if IP address is suspicious based on history."""
        # Check for high failure rate from this IP
        total_attempts = await db.execute(
            select(func.count(Payment.id)).where(Payment.ip_address == ip_address)
        )
        total = total_attempts.scalar() or 0

        if total < 5:  # Not enough data
            return False

        failed_attempts = await db.execute(
            select(func.count(Payment.id)).where(
                and_(
                    Payment.ip_address == ip_address,
                    Payment.status.in_(["failed", "cancelled"])
                )
            )
        )
        failed = failed_attempts.scalar() or 0

        failure_rate = failed / total if total > 0 else 0
        return failure_rate > 0.5  # More than 50% failure rate

    def _validate_email_domain(self, email: str) -> bool:
        """Validate email domain against known suspicious domains."""
        suspicious_domains = [
            "10minutemail.com", "guerrillamail.com", "mailinator.com",
            "tempmail.org", "throwaway.email", "temp-mail.org"
        ]

        domain = email.split("@")[-1].lower()
        return domain not in suspicious_domains

    def _is_suspicious_time(self) -> bool:
        """Check if current time is suspicious for transactions."""
        current_hour = datetime.utcnow().hour
        # Transactions between 2 AM and 5 AM UTC might be suspicious
        return 2 <= current_hour <= 5

    async def _handle_successful_payment(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Handle successful payment webhook."""
        reference = data.get("reference")
        payment = await self._get_payment_by_reference(db, reference)

        if payment:
            payment.status = "success"
            payment.paid_at = datetime.utcnow()
            payment.gateway_response = json.dumps(data)
            await db.commit()

            await self._audit_payment_action(
                db, payment.id, "webhook_success", None, ip_address,
                {"amount": float(payment.amount)}
            )

        return {"status": "processed", "reference": reference}

    async def _handle_failed_payment(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Handle failed payment webhook."""
        reference = data.get("reference")
        payment = await self._get_payment_by_reference(db, reference)

        if payment:
            payment.status = "failed"
            payment.gateway_response = json.dumps(data)
            await db.commit()

            await self._audit_payment_action(
                db, payment.id, "webhook_failed", None, ip_address,
                {"reason": data.get("gateway_response", "Unknown")}
            )

        return {"status": "processed", "reference": reference}

    async def _handle_successful_transfer(
        self,
        db: AsyncSession,
        data: Dict[str, Any],
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Handle successful transfer webhook (for vendor payouts)."""
        transfer_code = data.get("transfer_code")

        # Log transfer success
        await self._log_security_event(
            "transfer_successful",
            None,
            {
                "transfer_code": transfer_code,
                "amount": data.get("amount", 0) / 100,
                "recipient": data_masking.mask_account_number(data.get("recipient", {}).get("details", {}).get("account_number", ""))
            }
        )

        return {"status": "processed", "transfer_code": transfer_code}

    async def _audit_payment_action(
        self,
        db: AsyncSession,
        payment_id: str,
        action: str,
        user_id: str = None,
        ip_address: str = None,
        details: Dict[str, Any] = None
    ):
        """Audit payment actions for compliance."""
        audit_record = PaymentAudit(
            payment_id=payment_id,
            action=action,
            user_id=user_id,
            ip_address=ip_address,
            details=json.dumps(details or {}),
            created_at=datetime.utcnow()
        )

        db.add(audit_record)
        await db.commit()

    async def _log_security_event(
        self,
        event_type: str,
        user_id: Optional[str],
        details: Dict[str, Any]
    ):
        """Log security events for monitoring."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": "payment-service",
            "event_type": event_type,
            "user_id": user_id,
            "details": details
        }

        # Log to application logger
        if event_type in ["payment_fraud_detected", "webhook_signature_invalid", "payment_integrity_violation"]:
            logger.warning(f"Payment Security Event: {event}")
        else:
            logger.info(f"Payment Security Event: {event}")
