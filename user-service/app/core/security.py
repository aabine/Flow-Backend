from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import redis.asyncio as redis
import uuid
from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redis connection for token blacklist
_redis_client = None

async def get_redis_client():
    """Get Redis client for token blacklisting."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
    return _redis_client


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_settings().SECRET_KEY, algorithm=get_settings().ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token (basic verification only)."""
    try:
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=[get_settings().ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


async def is_token_blacklisted(jti: str) -> bool:
    """Check if token is blacklisted in Redis."""
    try:
        redis_client = await get_redis_client()
        result = await redis_client.get(f"blacklist:{jti}")
        return result is not None
    except Exception:
        # If Redis is unavailable, allow the token (fail open for availability)
        return False


async def blacklist_token(jti: str, exp: int) -> bool:
    """Add token to blacklist with expiration."""
    try:
        redis_client = await get_redis_client()
        # Calculate TTL based on token expiration
        ttl = max(0, exp - int(datetime.utcnow().timestamp()))
        if ttl > 0:
            await redis_client.setex(f"blacklist:{jti}", ttl, "1")
        return True
    except Exception:
        return False


async def cleanup_expired_blacklist_tokens() -> int:
    """Clean up expired tokens from blacklist (Redis handles this automatically with TTL)."""
    try:
        redis_client = await get_redis_client()
        # Get all blacklist keys
        keys = await redis_client.keys("blacklist:*")

        # Count expired keys (Redis automatically removes them, so this is just for monitoring)
        expired_count = 0
        for key in keys:
            ttl = await redis_client.ttl(key)
            if ttl == -2:  # Key doesn't exist (expired)
                expired_count += 1

        return expired_count
    except Exception:
        return 0


async def get_blacklist_stats() -> Dict[str, Any]:
    """Get blacklist statistics for monitoring."""
    try:
        redis_client = await get_redis_client()
        keys = await redis_client.keys("blacklist:*")

        total_blacklisted = len(keys)

        # Get memory usage info
        info = await redis_client.info('memory')
        memory_usage = info.get('used_memory_human', 'Unknown')

        return {
            "total_blacklisted_tokens": total_blacklisted,
            "redis_memory_usage": memory_usage,
            "blacklist_keys_sample": keys[:10] if keys else []
        }
    except Exception as e:
        return {
            "error": str(e),
            "total_blacklisted_tokens": 0,
            "redis_memory_usage": "Unknown"
        }


async def verify_token_with_session(token: str, db: AsyncSession) -> Dict[str, Any]:
    """Enhanced token verification that checks session status and blacklist."""
    # First, verify JWT signature and structure
    payload = verify_token(token)

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )

    # Check if token is blacklisted
    if await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked"
        )

    # Check if session is still active (only for access tokens)
    token_type = payload.get("type", "access")
    if token_type == "access":
        from app.models.user import UserSession

        result = await db.execute(
            select(UserSession).filter(
                and_(
                    UserSession.access_token_jti == jti,
                    UserSession.is_active == True,
                    UserSession.expires_at > datetime.utcnow()
                )
            )
        )

        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid"
            )

        # Update last activity
        session.last_activity = datetime.utcnow()
        await db.commit()

    return payload
