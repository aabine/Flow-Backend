"""
API Key authentication middleware for service-to-service communication.
Implements API key validation and permission checking.
"""

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.api_key_service import APIKeyService, APIKeyPermission
from app.core.database import get_db


class APIKeyAuth:
    """API Key authentication dependency."""
    
    def __init__(self, required_permission: Optional[str] = None):
        self.required_permission = required_permission
        self.security = HTTPBearer(auto_error=False)
    
    async def __call__(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
        db: AsyncSession = Depends(get_db)
    ) -> Dict[str, Any]:
        """Validate API key and return key information."""
        
        # Check for API key in Authorization header
        api_key = None
        
        if credentials and credentials.scheme.lower() == "bearer":
            api_key = credentials.credentials
        
        # Also check for API key in X-API-Key header
        if not api_key:
            api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate API key
        key_info = await APIKeyService().validate_api_key(
            db, api_key, self.required_permission
        )
        
        if not key_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return key_info


class ServiceAuth:
    """Service-to-service authentication with specific permissions."""
    
    @staticmethod
    def require_permission(permission: str):
        """Create dependency that requires specific permission."""
        return APIKeyAuth(required_permission=permission)
    
    @staticmethod
    def require_service_access():
        """Require service-level access."""
        return APIKeyAuth(required_permission=APIKeyPermission.SERVICE_INTERNAL.value)
    
    @staticmethod
    def require_user_read():
        """Require user read permission."""
        return APIKeyAuth(required_permission=APIKeyPermission.USER_READ.value)
    
    @staticmethod
    def require_user_write():
        """Require user write permission."""
        return APIKeyAuth(required_permission=APIKeyPermission.USER_WRITE.value)
    
    @staticmethod
    def require_admin():
        """Require admin permissions."""
        return APIKeyAuth(required_permission=APIKeyPermission.ADMIN_READ.value)


# Convenience instances
api_key_auth = APIKeyAuth()
service_auth = ServiceAuth.require_service_access()
user_read_auth = ServiceAuth.require_user_read()
user_write_auth = ServiceAuth.require_user_write()
admin_auth = ServiceAuth.require_admin()


def get_api_key_from_request(request: Request) -> Optional[str]:
    """Extract API key from request headers."""
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix
    
    # Check X-API-Key header
    return request.headers.get("X-API-Key")


async def validate_service_request(
    request: Request,
    db: AsyncSession,
    required_permission: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Validate service request with API key.
    Returns key info if valid, None if invalid.
    """
    api_key = get_api_key_from_request(request)
    if not api_key:
        return None
    
    return await APIKeyService().validate_api_key(db, api_key, required_permission)


class APIKeyMiddleware:
    """Middleware for API key authentication on specific routes."""
    
    def __init__(self, protected_paths: list = None):
        self.protected_paths = protected_paths or ["/api/", "/internal/"]
    
    def should_protect_path(self, path: str) -> bool:
        """Check if path should be protected with API key."""
        return any(protected in path for protected in self.protected_paths)
    
    async def authenticate_request(
        self,
        request: Request,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Authenticate request with API key if required."""
        
        if not self.should_protect_path(request.url.path):
            return None
        
        api_key = get_api_key_from_request(request)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required for this endpoint"
            )
        
        key_info = await APIKeyService().validate_api_key(db, api_key)
        if not key_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key"
            )
        
        return key_info


# Global middleware instance
api_key_middleware = APIKeyMiddleware()


# Utility functions for common authentication patterns
async def authenticate_service_call(
    request: Request,
    db: AsyncSession,
    required_permission: str = APIKeyPermission.SERVICE_INTERNAL.value
) -> Dict[str, Any]:
    """Authenticate service-to-service call."""
    
    api_key = get_api_key_from_request(request)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service authentication required"
        )
    
    key_info = await APIKeyService().validate_api_key(db, api_key, required_permission)
    if not key_info:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for service call"
        )
    
    return key_info


async def authenticate_webhook_call(
    request: Request,
    db: AsyncSession
) -> Dict[str, Any]:
    """Authenticate webhook call."""
    
    return await authenticate_service_call(
        request, db, APIKeyPermission.SERVICE_WEBHOOK.value
    )


async def authenticate_admin_call(
    request: Request,
    db: AsyncSession
) -> Dict[str, Any]:
    """Authenticate admin API call."""
    
    return await authenticate_service_call(
        request, db, APIKeyPermission.ADMIN_READ.value
    )
