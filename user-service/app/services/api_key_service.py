"""
API Key management service for service-to-service authentication.
Implements secure API key generation, validation, and management.
"""

import secrets
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, delete
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, APIKey
from app.core.config import get_settings
from shared.models import UserRole

settings = get_settings()


class APIKeyPermission(Enum):
    """API key permissions for fine-grained access control."""
    
    # User management
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    
    # Profile management
    PROFILE_READ = "profile:read"
    PROFILE_WRITE = "profile:write"
    
    # Authentication
    AUTH_VERIFY = "auth:verify"
    AUTH_REFRESH = "auth:refresh"
    
    # Service-to-service
    SERVICE_INTERNAL = "service:internal"
    SERVICE_WEBHOOK = "service:webhook"
    
    # Admin operations
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    
    # All permissions (for admin keys)
    ALL = "*"


class APIKeyService:
    """API key management and validation service."""
    
    def __init__(self):
        self.key_prefix_length = 8
        self.key_total_length = 64
        self.default_expiry_days = 365
    
    def _generate_api_key(self) -> Tuple[str, str, str]:
        """
        Generate secure API key.
        Returns (full_key, key_hash, key_prefix).
        """
        # Generate random key
        key = secrets.token_urlsafe(self.key_total_length)
        
        # Create hash for storage
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        # Extract prefix for identification
        key_prefix = key[:self.key_prefix_length]
        
        return key, key_hash, key_prefix
    
    def _validate_permissions(self, permissions: List[str]) -> bool:
        """Validate that all permissions are valid."""
        valid_permissions = {perm.value for perm in APIKeyPermission}
        return all(perm in valid_permissions for perm in permissions)
    
    async def create_api_key(
        self,
        db: AsyncSession,
        key_name: str,
        permissions: List[str],
        user_id: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        created_by_ip: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Create new API key.
        Returns dict with key information (including the actual key).
        """
        try:
            # Validate permissions
            if not self._validate_permissions(permissions):
                raise ValueError("Invalid permissions specified")
            
            # Generate key
            api_key, key_hash, key_prefix = self._generate_api_key()
            
            # Set expiration
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            elif expires_in_days is None:  # Use default
                expires_at = datetime.utcnow() + timedelta(days=self.default_expiry_days)
            
            # Create API key record
            api_key_record = APIKey(
                user_id=user_id,
                key_name=key_name,
                key_hash=key_hash,
                key_prefix=key_prefix,
                permissions=json.dumps(permissions),
                expires_at=expires_at,
                created_by_ip=created_by_ip
            )
            
            db.add(api_key_record)
            await db.commit()
            await db.refresh(api_key_record)
            
            return {
                "id": str(api_key_record.id),
                "api_key": api_key,  # Only returned during creation
                "key_name": key_name,
                "key_prefix": key_prefix,
                "permissions": permissions,
                "expires_at": expires_at,
                "created_at": api_key_record.created_at,
                "warning": "Store this API key securely. It will not be shown again."
            }
            
        except Exception as e:
            await db.rollback()
            raise ValueError(f"Failed to create API key: {str(e)}")
    
    async def validate_api_key(
        self,
        db: AsyncSession,
        api_key: str,
        required_permission: Optional[str] = None
    ) -> Optional[Dict[str, any]]:
        """
        Validate API key and check permissions.
        Returns key info if valid, None if invalid.
        """
        try:
            # Hash the provided key
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            
            # Find API key in database
            result = await db.execute(
                select(APIKey).filter(
                    and_(
                        APIKey.key_hash == key_hash,
                        APIKey.is_active == True,
                        APIKey.expires_at > datetime.utcnow()
                    )
                )
            )
            
            api_key_record = result.scalar_one_or_none()
            if not api_key_record:
                return None
            
            # Parse permissions
            permissions = json.loads(api_key_record.permissions or "[]")
            
            # Check required permission
            if required_permission:
                has_permission = (
                    APIKeyPermission.ALL.value in permissions or
                    required_permission in permissions
                )
                if not has_permission:
                    return None
            
            # Update usage statistics
            api_key_record.last_used_at = datetime.utcnow()
            api_key_record.usage_count += 1
            await db.commit()
            
            # Get user info if associated
            user_info = None
            if api_key_record.user_id:
                user_result = await db.execute(
                    select(User).filter(User.id == api_key_record.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    user_info = {
                        "id": str(user.id),
                        "email": user.email,
                        "role": user.role.value,
                        "is_active": user.is_active
                    }
            
            return {
                "id": str(api_key_record.id),
                "key_name": api_key_record.key_name,
                "key_prefix": api_key_record.key_prefix,
                "permissions": permissions,
                "user_id": str(api_key_record.user_id) if api_key_record.user_id else None,
                "user": user_info,
                "last_used_at": api_key_record.last_used_at,
                "usage_count": api_key_record.usage_count,
                "created_at": api_key_record.created_at
            }
            
        except Exception as e:
            print(f"API key validation error: {e}")
            return None
    
    async def list_api_keys(
        self,
        db: AsyncSession,
        user_id: Optional[str] = None,
        include_inactive: bool = False
    ) -> List[Dict[str, any]]:
        """List API keys for a user or all keys."""
        try:
            query = select(APIKey)
            
            conditions = []
            if user_id:
                import uuid
                conditions.append(APIKey.user_id == uuid.UUID(user_id))
            
            if not include_inactive:
                conditions.append(APIKey.is_active == True)
            
            if conditions:
                query = query.filter(and_(*conditions))
            
            query = query.order_by(APIKey.created_at.desc())
            
            result = await db.execute(query)
            api_keys = result.scalars().all()
            
            return [
                {
                    "id": str(key.id),
                    "key_name": key.key_name,
                    "key_prefix": key.key_prefix,
                    "permissions": json.loads(key.permissions or "[]"),
                    "is_active": key.is_active,
                    "expires_at": key.expires_at,
                    "last_used_at": key.last_used_at,
                    "usage_count": key.usage_count,
                    "created_at": key.created_at,
                    "user_id": str(key.user_id) if key.user_id else None
                }
                for key in api_keys
            ]
            
        except Exception as e:
            print(f"Error listing API keys: {e}")
            return []
    
    async def revoke_api_key(
        self,
        db: AsyncSession,
        key_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Revoke (deactivate) an API key."""
        try:
            import uuid
            
            conditions = [APIKey.id == uuid.UUID(key_id)]
            if user_id:
                conditions.append(APIKey.user_id == uuid.UUID(user_id))
            
            stmt = update(APIKey).where(
                and_(*conditions)
            ).values(
                is_active=False,
                updated_at=datetime.utcnow()
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            print(f"Error revoking API key: {e}")
            return False
    
    async def delete_api_key(
        self,
        db: AsyncSession,
        key_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Permanently delete an API key."""
        try:
            import uuid
            
            conditions = [APIKey.id == uuid.UUID(key_id)]
            if user_id:
                conditions.append(APIKey.user_id == uuid.UUID(user_id))
            
            stmt = delete(APIKey).where(and_(*conditions))
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            print(f"Error deleting API key: {e}")
            return False
    
    async def rotate_api_key(
        self,
        db: AsyncSession,
        key_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, any]]:
        """Rotate an API key (generate new key, keep same permissions)."""
        try:
            import uuid
            
            # Get existing key
            conditions = [APIKey.id == uuid.UUID(key_id)]
            if user_id:
                conditions.append(APIKey.user_id == uuid.UUID(user_id))
            
            result = await db.execute(
                select(APIKey).filter(and_(*conditions))
            )
            
            existing_key = result.scalar_one_or_none()
            if not existing_key:
                return None
            
            # Generate new key
            new_api_key, new_key_hash, new_key_prefix = self._generate_api_key()
            
            # Update existing record
            existing_key.key_hash = new_key_hash
            existing_key.key_prefix = new_key_prefix
            existing_key.updated_at = datetime.utcnow()
            existing_key.usage_count = 0  # Reset usage count
            existing_key.last_used_at = None
            
            await db.commit()
            
            return {
                "id": str(existing_key.id),
                "api_key": new_api_key,  # Only returned during rotation
                "key_name": existing_key.key_name,
                "key_prefix": new_key_prefix,
                "permissions": json.loads(existing_key.permissions or "[]"),
                "warning": "Store this new API key securely. The old key is now invalid."
            }
            
        except Exception as e:
            await db.rollback()
            print(f"Error rotating API key: {e}")
            return None
    
    async def cleanup_expired_keys(self, db: AsyncSession) -> int:
        """Clean up expired API keys."""
        try:
            stmt = update(APIKey).where(
                and_(
                    APIKey.expires_at < datetime.utcnow(),
                    APIKey.is_active == True
                )
            ).values(
                is_active=False,
                updated_at=datetime.utcnow()
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount
            
        except Exception as e:
            print(f"Error cleaning up expired keys: {e}")
            return 0


# Global API key service instance
api_key_service = APIKeyService()
