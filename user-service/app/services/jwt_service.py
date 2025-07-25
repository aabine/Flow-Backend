"""
Enhanced JWT service with refresh token support and session management.
Implements secure token rotation and session tracking.
"""

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, delete
from jose import JWTError, jwt
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, UserSession
from app.core.config import get_settings
from shared.models import UserRole

settings = get_settings()


class JWTService:
    """Enhanced JWT service with refresh token support."""
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = 7  # 7 days for refresh tokens
    
    def create_access_token(
        self, 
        user_id: str, 
        email: str, 
        role: UserRole,
        jti: str = None
    ) -> str:
        """Create JWT access token."""
        if not jti:
            jti = secrets.token_urlsafe(16)
        
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        payload = {
            "sub": email,
            "user_id": user_id,
            "role": role.value if isinstance(role, UserRole) else role,
            "type": "access",
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": jti,
            "iss": "oxygen-platform"
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(
        self, 
        user_id: str, 
        email: str, 
        role: UserRole,
        jti: str = None
    ) -> str:
        """Create JWT refresh token."""
        if not jti:
            jti = secrets.token_urlsafe(16)
        
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            "sub": email,
            "user_id": user_id,
            "role": role.value if isinstance(role, UserRole) else role,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": jti,
            "iss": "oxygen-platform"
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            raise ValueError(f"Invalid token: {str(e)}")
    
    async def create_user_session(
        self,
        db: AsyncSession,
        user: User,
        ip_address: str = None,
        user_agent: str = None,
        remember_me: bool = False
    ) -> Dict[str, Any]:
        """Create new user session with tokens."""
        
        # Generate unique JTIs for tokens
        access_jti = secrets.token_urlsafe(16)
        refresh_jti = secrets.token_urlsafe(16)
        
        # Create tokens
        access_token = self.create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            jti=access_jti
        )
        
        # Extend refresh token expiry for "remember me"
        refresh_expire_days = 30 if remember_me else self.refresh_token_expire_days
        
        refresh_token = self.create_refresh_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            jti=refresh_jti
        )
        
        # Create session record
        session_expires = datetime.utcnow() + timedelta(days=refresh_expire_days)
        
        session = UserSession(
            user_id=user.id,
            access_token_jti=access_jti,
            refresh_token_jti=refresh_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=session_expires,
            last_activity=datetime.utcnow(),
            is_active=True
        )
        
        db.add(session)
        await db.commit()
        await db.refresh(session)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
            "session_id": str(session.id)
        }
    
    async def refresh_access_token(
        self,
        db: AsyncSession,
        refresh_token: str,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        
        try:
            # Verify refresh token
            payload = self.verify_token(refresh_token)
            
            if payload.get("type") != "refresh":
                raise ValueError("Invalid token type")
            
            refresh_jti = payload.get("jti")
            user_id = payload.get("user_id")
            
            # Find active session
            result = await db.execute(
                select(UserSession).filter(
                    and_(
                        UserSession.refresh_token_jti == refresh_jti,
                        UserSession.is_active == True,
                        UserSession.expires_at > datetime.utcnow()
                    )
                )
            )
            
            session = result.scalar_one_or_none()
            if not session:
                raise ValueError("Invalid or expired session")
            
            # Get user
            user_result = await db.execute(
                select(User).filter(User.id == uuid.UUID(user_id))
            )
            user = user_result.scalar_one_or_none()
            if not user or not user.is_active:
                raise ValueError("User not found or inactive")
            
            # Generate new tokens (token rotation)
            new_access_jti = secrets.token_urlsafe(16)
            new_refresh_jti = secrets.token_urlsafe(16)
            
            new_access_token = self.create_access_token(
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                jti=new_access_jti
            )
            
            new_refresh_token = self.create_refresh_token(
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                jti=new_refresh_jti
            )
            
            # Update session with new tokens
            session.access_token_jti = new_access_jti
            session.refresh_token_jti = new_refresh_jti
            session.last_activity = datetime.utcnow()
            if ip_address:
                session.ip_address = ip_address
            
            await db.commit()
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }
            
        except Exception as e:
            raise ValueError(f"Token refresh failed: {str(e)}")
    
    async def revoke_session(self, db: AsyncSession, session_id: str) -> bool:
        """Revoke a specific session."""
        try:
            stmt = update(UserSession).where(
                UserSession.id == uuid.UUID(session_id)
            ).values(
                is_active=False,
                logged_out_at=datetime.utcnow()
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount > 0
        except Exception:
            return False
    
    async def revoke_all_user_sessions(self, db: AsyncSession, user_id: str) -> int:
        """Revoke all sessions for a user."""
        try:
            stmt = update(UserSession).where(
                UserSession.user_id == uuid.UUID(user_id)
            ).values(
                is_active=False,
                logged_out_at=datetime.utcnow()
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount
        except Exception:
            return 0
    
    async def get_user_sessions(self, db: AsyncSession, user_id: str) -> list:
        """Get all active sessions for a user."""
        try:
            result = await db.execute(
                select(UserSession).filter(
                    and_(
                        UserSession.user_id == uuid.UUID(user_id),
                        UserSession.is_active == True
                    )
                ).order_by(UserSession.last_activity.desc())
            )
            
            sessions = result.scalars().all()
            
            return [
                {
                    "id": str(session.id),
                    "ip_address": session.ip_address,
                    "user_agent": session.user_agent,
                    "created_at": session.created_at,
                    "last_activity": session.last_activity,
                    "expires_at": session.expires_at
                }
                for session in sessions
            ]
        except Exception:
            return []
    
    async def cleanup_expired_sessions(self, db: AsyncSession) -> int:
        """Clean up expired sessions."""
        try:
            stmt = update(UserSession).where(
                UserSession.expires_at < datetime.utcnow()
            ).values(
                is_active=False,
                logged_out_at=datetime.utcnow()
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            return result.rowcount
        except Exception:
            return 0


# Global JWT service instance
jwt_service = JWTService()
