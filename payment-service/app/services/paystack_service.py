import httpx
import hmac
import hashlib
from typing import Dict, Any, Optional
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import settings


class PaystackService:
    def __init__(self):
        self.base_url = "https://api.paystack.co"
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Paystack API requests."""
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

    async def initialize_transaction(self, email: str, amount: int, reference: str, callback_url: Optional[str] = None) -> Dict[str, Any]:
        """Initialize a transaction with Paystack."""
        url = f"{self.base_url}/transaction/initialize"
        
        data = {
            "email": email,
            "amount": amount,  # Amount in kobo
            "reference": reference,
            "currency": "NGN"
        }
        
        if callback_url:
            data["callback_url"] = callback_url

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=self._get_headers())
            return response.json()

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """Verify a transaction with Paystack."""
        url = f"{self.base_url}/transaction/verify/{reference}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())
            return response.json()

    async def create_split(self, name: str, type: str, currency: str, subaccounts: list) -> Dict[str, Any]:
        """Create a transaction split."""
        url = f"{self.base_url}/split"
        
        data = {
            "name": name,
            "type": type,
            "currency": currency,
            "subaccounts": subaccounts
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=self._get_headers())
            return response.json()

    async def refund_transaction(self, transaction_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """Refund a transaction."""
        url = f"{self.base_url}/refund"
        
        data = {"transaction": transaction_id}
        if amount:
            data["amount"] = amount

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=self._get_headers())
            return response.json()

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature."""
        expected_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

    async def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Get transaction details."""
        url = f"{self.base_url}/transaction/{transaction_id}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self._get_headers())
            return response.json()

    async def list_transactions(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """List transactions."""
        url = f"{self.base_url}/transaction"
        params = {"page": page, "perPage": per_page}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=self._get_headers())
            return response.json()
