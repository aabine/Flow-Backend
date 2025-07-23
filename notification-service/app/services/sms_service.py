import logging
from typing import Optional, Dict, Any
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class SMSService:
    """
    SMS Service for sending SMS notifications.
    This is a basic implementation that can be extended with actual SMS providers.
    """
    
    def __init__(self):
        self.api_key = settings.SMS_API_KEY
        self.sender_id = settings.SMS_SENDER_ID
        self.enabled = bool(self.api_key)  # Only enable if API key is provided
        
        if not self.enabled:
            logger.warning("SMS service is disabled - no API key provided")
    
    async def send_sms(
        self,
        to_phone: str,
        message: str,
        sender_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an SMS message.
        
        Args:
            to_phone: Recipient phone number (with country code)
            message: SMS message content
            sender_id: Optional sender ID (defaults to configured sender)
            metadata: Optional metadata for tracking
            
        Returns:
            bool: True if SMS was sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(f"SMS service disabled - cannot send SMS to {to_phone}")
            return False
        
        if not to_phone or not message:
            logger.error("Phone number and message are required for SMS")
            return False
        
        # Clean phone number (remove spaces, dashes, etc.)
        clean_phone = self._clean_phone_number(to_phone)
        if not clean_phone:
            logger.error(f"Invalid phone number format: {to_phone}")
            return False
        
        sender = sender_id or self.sender_id
        
        try:
            # This is a placeholder implementation
            # In a real implementation, you would integrate with an SMS provider like:
            # - Twilio
            # - AWS SNS
            # - Africa's Talking
            # - Termii
            # - etc.
            
            logger.info(f"Sending SMS to {clean_phone}: {message[:50]}...")
            
            # Simulate SMS sending for now
            # Replace this with actual SMS provider integration
            success = await self._send_via_provider(clean_phone, message, sender, metadata)
            
            if success:
                logger.info(f"SMS sent successfully to {clean_phone}")
            else:
                logger.error(f"Failed to send SMS to {clean_phone}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending SMS to {clean_phone}: {e}")
            return False
    
    async def _send_via_provider(
        self,
        phone: str,
        message: str,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send SMS via the configured provider.
        This is a placeholder that should be replaced with actual provider integration.
        """
        # For now, just log the SMS (in development mode)
        if settings.ENVIRONMENT == "development":
            logger.info(f"[SMS SIMULATION] To: {phone}, From: {sender}, Message: {message}")
            return True
        
        # In production, integrate with actual SMS provider
        # Example for a generic REST API:
        try:
            payload = {
                "to": phone,
                "message": message,
                "sender": sender,
                "api_key": self.api_key
            }
            
            # This is just an example - replace with actual provider endpoint
            # response = requests.post(
            #     "https://api.sms-provider.com/send",
            #     json=payload,
            #     timeout=30
            # )
            # return response.status_code == 200
            
            # For now, return True to simulate success
            logger.warning("SMS provider not configured - using simulation mode")
            return True
            
        except Exception as e:
            logger.error(f"SMS provider error: {e}")
            return False
    
    def _clean_phone_number(self, phone: str) -> Optional[str]:
        """
        Clean and validate phone number format.
        
        Args:
            phone: Raw phone number string
            
        Returns:
            str: Cleaned phone number or None if invalid
        """
        if not phone:
            return None
        
        # Remove common formatting characters
        cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        # Basic validation - should start with + and contain only digits after that
        if cleaned.startswith("+") and cleaned[1:].isdigit() and len(cleaned) >= 10:
            return cleaned
        
        # If no country code, assume it's a local number and needs formatting
        # This is very basic - in production you'd want more sophisticated validation
        if cleaned.isdigit() and len(cleaned) >= 10:
            # For Nigerian numbers, add +234 if missing (example)
            if len(cleaned) == 11 and cleaned.startswith("0"):
                return f"+234{cleaned[1:]}"
            elif len(cleaned) == 10:
                return f"+234{cleaned}"
        
        return None
    
    async def send_bulk_sms(
        self,
        recipients: list[str],
        message: str,
        sender_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        """
        Send SMS to multiple recipients.
        
        Args:
            recipients: List of phone numbers
            message: SMS message content
            sender_id: Optional sender ID
            metadata: Optional metadata
            
        Returns:
            dict: Mapping of phone numbers to success status
        """
        results = {}
        
        for phone in recipients:
            success = await self.send_sms(phone, message, sender_id, metadata)
            results[phone] = success
        
        return results


# Create a singleton instance
sms_service = SMSService()
