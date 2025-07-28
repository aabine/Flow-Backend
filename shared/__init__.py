"""
Shared utilities and models for the Oxygen Supply Platform.
"""

from .exceptions import (
    PlatformException,
    AuthException,
    AuthorizationException,
    TokenException,
    ValidationException,
    DatabaseException,
    ServiceException,
    PaymentException,
    InventoryException,
    OrderException,
    NotificationException,
    WebSocketException,
    RateLimitException,
    SecurityException
)

# Import authentication dependencies if FastAPI is available
try:
    from .security.auth import (
        get_current_user,
        get_current_user_optional,
        get_current_admin_user
    )
    _auth_available = True
except ImportError:
    _auth_available = False

__all__ = [
    "PlatformException",
    "AuthException",
    "AuthorizationException",
    "TokenException",
    "ValidationException",
    "DatabaseException",
    "ServiceException",
    "PaymentException",
    "InventoryException",
    "OrderException",
    "NotificationException",
    "WebSocketException",
    "RateLimitException",
    "SecurityException"
]

# Add authentication functions to __all__ if available
if _auth_available:
    __all__.extend([
        "get_current_user",
        "get_current_user_optional",
        "get_current_admin_user"
    ])