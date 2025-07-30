"""
Rate limiting and brute force protection service.
Implements Redis-based rate limiting with sliding window and account lockout.
"""

import redis
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, LoginAttempt
from app.core.config import get_settings

settings = get_settings()


class RateLimitConfig:
    """Rate limiting configuration."""
    
    # Login attempts
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_WINDOW_MINUTES = 15
    LOGIN_LOCKOUT_MINUTES = 30
    
    # API rate limits
    API_MAX_REQUESTS = 100
    API_WINDOW_MINUTES = 1
    
    # Password reset
    PASSWORD_RESET_MAX_ATTEMPTS = 3
    PASSWORD_RESET_WINDOW_MINUTES = 60
    
    # Email verification
    EMAIL_VERIFICATION_MAX_ATTEMPTS = 5
    EMAIL_VERIFICATION_WINDOW_MINUTES = 60

    # Registration
    REGISTRATION_MAX_ATTEMPTS = 5
    REGISTRATION_WINDOW_MINUTES = 60


class RateLimitService:
    """Rate limiting and brute force protection service."""
    
    def __init__(self):
        try:
            self.redis_client = redis.from_url(
                getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0'),
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.redis_available = True
        except Exception as e:
            print(f"⚠️ Redis not available, rate limiting disabled: {e}")
            self.redis_available = False
            self.redis_client = None
        
        self.config = RateLimitConfig()
    
    def _get_key(self, key_type: str, identifier: str) -> str:
        """Generate Redis key for rate limiting."""
        return f"rate_limit:{key_type}:{identifier}"
    
    def _get_sliding_window_key(self, key_type: str, identifier: str, window_start: int) -> str:
        """Generate sliding window key."""
        return f"rate_limit:{key_type}:{identifier}:{window_start}"
    
    async def check_rate_limit(
        self,
        key_type: str,
        identifier: str,
        max_attempts: int,
        window_minutes: int
    ) -> Tuple[bool, int, int]:
        """
        Check rate limit using sliding window.
        Returns (is_allowed, current_count, remaining_attempts).
        """
        if not self.redis_available:
            return True, 0, max_attempts  # Allow if Redis unavailable
        
        try:
            now = datetime.utcnow()
            window_start = int(now.timestamp()) // (window_minutes * 60)
            current_window_key = self._get_sliding_window_key(key_type, identifier, window_start)
            previous_window_key = self._get_sliding_window_key(key_type, identifier, window_start - 1)
            
            # Get counts from current and previous windows
            pipe = self.redis_client.pipeline()
            pipe.get(current_window_key)
            pipe.get(previous_window_key)
            results = pipe.execute()
            
            current_count = int(results[0] or 0)
            previous_count = int(results[1] or 0)
            
            # Calculate weighted count (sliding window)
            window_seconds = window_minutes * 60
            elapsed_in_current_window = int(now.timestamp()) % window_seconds
            weight = elapsed_in_current_window / window_seconds
            
            weighted_count = int(previous_count * (1 - weight) + current_count)
            
            is_allowed = weighted_count < max_attempts
            remaining = max(0, max_attempts - weighted_count)
            
            return is_allowed, weighted_count, remaining
            
        except Exception as e:
            print(f"Rate limit check error: {e}")
            return True, 0, max_attempts  # Allow on error
    
    async def increment_rate_limit(
        self,
        key_type: str,
        identifier: str,
        window_minutes: int
    ) -> int:
        """
        Increment rate limit counter.
        Returns new count.
        """
        if not self.redis_available:
            return 1
        
        try:
            now = datetime.utcnow()
            window_start = int(now.timestamp()) // (window_minutes * 60)
            window_key = self._get_sliding_window_key(key_type, identifier, window_start)
            
            pipe = self.redis_client.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, window_minutes * 60 * 2)  # Keep for 2 windows
            results = pipe.execute()
            
            return results[0]
            
        except Exception as e:
            print(f"Rate limit increment error: {e}")
            return 1
    
    async def check_login_rate_limit(self, identifier: str) -> Tuple[bool, int, int]:
        """Check login rate limit for IP or email."""
        return await self.check_rate_limit(
            "login",
            identifier,
            self.config.LOGIN_MAX_ATTEMPTS,
            self.config.LOGIN_WINDOW_MINUTES
        )
    
    async def increment_login_attempts(self, identifier: str) -> int:
        """Increment login attempts counter."""
        return await self.increment_rate_limit(
            "login",
            identifier,
            self.config.LOGIN_WINDOW_MINUTES
        )
    
    async def check_api_rate_limit(self, identifier: str) -> Tuple[bool, int, int]:
        """Check API rate limit."""
        return await self.check_rate_limit(
            "api",
            identifier,
            self.config.API_MAX_REQUESTS,
            self.config.API_WINDOW_MINUTES
        )
    
    async def increment_api_requests(self, identifier: str) -> int:
        """Increment API requests counter."""
        return await self.increment_rate_limit(
            "api",
            identifier,
            self.config.API_WINDOW_MINUTES
        )
    
    async def check_password_reset_rate_limit(self, identifier: str) -> Tuple[bool, int, int]:
        """Check password reset rate limit."""
        return await self.check_rate_limit(
            "password_reset",
            identifier,
            self.config.PASSWORD_RESET_MAX_ATTEMPTS,
            self.config.PASSWORD_RESET_WINDOW_MINUTES
        )
    
    async def increment_password_reset_attempts(self, identifier: str) -> int:
        """Increment password reset attempts."""
        return await self.increment_rate_limit(
            "password_reset",
            identifier,
            self.config.PASSWORD_RESET_WINDOW_MINUTES
        )
    
    async def check_email_verification_rate_limit(self, identifier: str) -> Tuple[bool, int, int]:
        """Check email verification rate limit."""
        return await self.check_rate_limit(
            "email_verification",
            identifier,
            self.config.EMAIL_VERIFICATION_MAX_ATTEMPTS,
            self.config.EMAIL_VERIFICATION_WINDOW_MINUTES
        )
    
    async def increment_email_verification_attempts(self, identifier: str) -> int:
        """Increment email verification attempts."""
        return await self.increment_rate_limit(
            "email_verification",
            identifier,
            self.config.EMAIL_VERIFICATION_WINDOW_MINUTES
        )

    async def check_registration_rate_limit(self, identifier: str) -> Tuple[bool, int, int]:
        """Check registration rate limit."""
        return await self.check_rate_limit(
            "registration",
            identifier,
            self.config.REGISTRATION_MAX_ATTEMPTS,
            self.config.REGISTRATION_WINDOW_MINUTES
        )

    async def increment_registration_attempts(self, identifier: str) -> int:
        """Increment registration attempts."""
        return await self.increment_rate_limit(
            "registration",
            identifier,
            self.config.REGISTRATION_WINDOW_MINUTES
        )
    
    async def record_login_attempt(
        self,
        db: AsyncSession,
        email: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        failure_reason: str = None,
        user_id: str = None
    ) -> None:
        """Record login attempt in database."""
        try:
            login_attempt = LoginAttempt(
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                failure_reason=failure_reason,
                attempted_at=datetime.utcnow()
            )
            
            db.add(login_attempt)
            await db.commit()
            
        except Exception as e:
            print(f"Failed to record login attempt: {e}")
    
    async def check_account_lockout(
        self,
        db: AsyncSession,
        email: str
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Check if account is locked due to failed attempts.
        Returns (is_locked, locked_until).
        """
        try:
            # Get user
            result = await db.execute(
                select(User).filter(User.email == email)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False, None
            
            # Check if account is currently locked
            if user.account_locked_until and user.account_locked_until > datetime.utcnow():
                return True, user.account_locked_until
            
            # Check recent failed attempts
            recent_attempts = await db.execute(
                select(LoginAttempt).filter(
                    LoginAttempt.email == email,
                    LoginAttempt.success == False,
                    LoginAttempt.attempted_at > datetime.utcnow() - timedelta(minutes=self.config.LOGIN_WINDOW_MINUTES)
                ).order_by(LoginAttempt.attempted_at.desc())
            )
            
            failed_attempts = recent_attempts.scalars().all()
            
            if len(failed_attempts) >= self.config.LOGIN_MAX_ATTEMPTS:
                # Lock account
                locked_until = datetime.utcnow() + timedelta(minutes=self.config.LOGIN_LOCKOUT_MINUTES)
                
                await db.execute(
                    update(User).where(User.id == user.id).values(
                        failed_login_attempts=len(failed_attempts),
                        account_locked_until=locked_until
                    )
                )
                await db.commit()
                
                return True, locked_until
            
            return False, None
            
        except Exception as e:
            print(f"Account lockout check error: {e}")
            return False, None
    
    async def unlock_account(self, db: AsyncSession, email: str) -> bool:
        """Unlock user account."""
        try:
            result = await db.execute(
                update(User).where(User.email == email).values(
                    failed_login_attempts=0,
                    account_locked_until=None
                )
            )
            await db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            print(f"Account unlock error: {e}")
            return False
    
    async def reset_failed_attempts(self, db: AsyncSession, email: str) -> bool:
        """Reset failed login attempts for user."""
        try:
            result = await db.execute(
                update(User).where(User.email == email).values(
                    failed_login_attempts=0
                )
            )
            await db.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            print(f"Reset failed attempts error: {e}")
            return False
    
    async def get_rate_limit_info(self, key_type: str, identifier: str) -> Dict[str, any]:
        """Get current rate limit information."""
        if not self.redis_available:
            return {
                "current_count": 0,
                "limit": 0,
                "remaining": 0,
                "reset_time": None
            }
        
        try:
            # Get configuration based on key type
            config_map = {
                "login": (self.config.LOGIN_MAX_ATTEMPTS, self.config.LOGIN_WINDOW_MINUTES),
                "api": (self.config.API_MAX_REQUESTS, self.config.API_WINDOW_MINUTES),
                "password_reset": (self.config.PASSWORD_RESET_MAX_ATTEMPTS, self.config.PASSWORD_RESET_WINDOW_MINUTES),
                "email_verification": (self.config.EMAIL_VERIFICATION_MAX_ATTEMPTS, self.config.EMAIL_VERIFICATION_WINDOW_MINUTES)
            }
            
            max_attempts, window_minutes = config_map.get(key_type, (100, 1))
            
            is_allowed, current_count, remaining = await self.check_rate_limit(
                key_type, identifier, max_attempts, window_minutes
            )
            
            # Calculate reset time
            now = datetime.utcnow()
            window_start = int(now.timestamp()) // (window_minutes * 60)
            next_window = (window_start + 1) * (window_minutes * 60)
            reset_time = datetime.fromtimestamp(next_window)
            
            return {
                "current_count": current_count,
                "limit": max_attempts,
                "remaining": remaining,
                "reset_time": reset_time,
                "is_allowed": is_allowed
            }
            
        except Exception as e:
            print(f"Get rate limit info error: {e}")
            return {
                "current_count": 0,
                "limit": max_attempts,
                "remaining": max_attempts,
                "reset_time": None,
                "is_allowed": True
            }


# Global rate limit service instance
rate_limit_service = RateLimitService()
