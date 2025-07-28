"""
Shared exception classes for the Oxygen Supply Platform.
Provides custom exceptions for authentication, authorization, and other common errors.
"""

from typing import Optional, Dict, Any


class PlatformException(Exception):
    """Base exception class for all platform-specific exceptions."""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class AuthException(PlatformException):
    """Exception raised for authentication-related errors."""
    
    def __init__(self, message: str = "Authentication failed", error_code: str = "AUTH_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class AuthorizationException(PlatformException):
    """Exception raised for authorization-related errors."""
    
    def __init__(self, message: str = "Access denied", error_code: str = "AUTHZ_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class TokenException(AuthException):
    """Exception raised for JWT token-related errors."""
    
    def __init__(self, message: str = "Invalid token", error_code: str = "TOKEN_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class ValidationException(PlatformException):
    """Exception raised for data validation errors."""
    
    def __init__(self, message: str = "Validation failed", error_code: str = "VALIDATION_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class DatabaseException(PlatformException):
    """Exception raised for database-related errors."""
    
    def __init__(self, message: str = "Database error", error_code: str = "DB_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class ServiceException(PlatformException):
    """Exception raised for service-related errors."""
    
    def __init__(self, message: str = "Service error", error_code: str = "SERVICE_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class PaymentException(PlatformException):
    """Exception raised for payment-related errors."""
    
    def __init__(self, message: str = "Payment error", error_code: str = "PAYMENT_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class InventoryException(PlatformException):
    """Exception raised for inventory-related errors."""
    
    def __init__(self, message: str = "Inventory error", error_code: str = "INVENTORY_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class OrderException(PlatformException):
    """Exception raised for order-related errors."""
    
    def __init__(self, message: str = "Order error", error_code: str = "ORDER_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class NotificationException(PlatformException):
    """Exception raised for notification-related errors."""
    
    def __init__(self, message: str = "Notification error", error_code: str = "NOTIFICATION_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class WebSocketException(PlatformException):
    """Exception raised for WebSocket-related errors."""
    
    def __init__(self, message: str = "WebSocket error", error_code: str = "WEBSOCKET_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class RateLimitException(PlatformException):
    """Exception raised when rate limits are exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", error_code: str = "RATE_LIMIT_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)


class SecurityException(PlatformException):
    """Exception raised for security-related errors."""
    
    def __init__(self, message: str = "Security violation", error_code: str = "SECURITY_ERROR", details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)
