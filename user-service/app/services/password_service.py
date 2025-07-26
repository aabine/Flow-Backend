"""
Password management service with comprehensive security features.
Implements password validation, reset functionality, and history tracking.
"""

import secrets
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from passlib.context import CryptContext
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, PasswordResetToken
from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


class PasswordPolicy:
    """Password policy configuration and validation."""
    
    MIN_LENGTH = 8
    MAX_LENGTH = 128
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGITS = True
    REQUIRE_SPECIAL = True
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    HISTORY_COUNT = 5  # Number of previous passwords to check
    
    # Common weak passwords to reject
    WEAK_PASSWORDS = {
        "password", "123456", "123456789", "qwerty", "abc123",
        "password123", "admin", "letmein", "welcome", "monkey",
        "dragon", "master", "shadow", "superman", "michael"
    }


class PasswordService:
    """Enhanced password management service."""
    
    def __init__(self):
        self.policy = PasswordPolicy()
    
    def validate_password_strength(self, password: str) -> Dict[str, any]:
        """
        Comprehensive password strength validation.
        Returns validation result with detailed feedback.
        """
        errors = []
        score = 0
        
        # Length check
        if len(password) < self.policy.MIN_LENGTH:
            errors.append(f"Password must be at least {self.policy.MIN_LENGTH} characters long")
        elif len(password) >= 12:
            score += 2
        else:
            score += 1
            
        if len(password) > self.policy.MAX_LENGTH:
            errors.append(f"Password must not exceed {self.policy.MAX_LENGTH} characters")
        
        # Character requirements
        if self.policy.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        else:
            score += 1
            
        if self.policy.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        else:
            score += 1
            
        if self.policy.REQUIRE_DIGITS and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        else:
            score += 1
            
        if self.policy.REQUIRE_SPECIAL and not re.search(f'[{re.escape(self.policy.SPECIAL_CHARS)}]', password):
            errors.append(f"Password must contain at least one special character: {self.policy.SPECIAL_CHARS}")
        else:
            score += 1
        
        # Common password check
        if password.lower() in self.policy.WEAK_PASSWORDS:
            errors.append("Password is too common and easily guessable")
        
        # Sequential characters check
        if self._has_sequential_chars(password):
            errors.append("Password should not contain long sequential characters (e.g., 1234, abcd)")
            score -= 1
        
        # Repeated characters check
        if self._has_repeated_chars(password):
            errors.append("Password should not contain too many repeated characters")
            score -= 1
        
        # Calculate strength
        strength = "weak"
        if score >= 6:
            strength = "strong"
        elif score >= 4:
            strength = "medium"
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "strength": strength,
            "score": max(0, score)
        }
    
    def _has_sequential_chars(self, password: str) -> bool:
        """Check for sequential characters (only long sequences are problematic)."""
        # Only check for longer sequences (4+ characters) or very common ones
        problematic_sequences = [
            "1234", "2345", "3456", "4567", "5678", "6789", "7890",
            "abcd", "bcde", "cdef", "defg", "efgh", "fghi", "ghij",
            "hijk", "ijkl", "jklm", "klmn", "lmno", "mnop", "nopq",
            "opqr", "pqrs", "qrst", "rstu", "stuv", "tuvw", "uvwx",
            "vwxy", "wxyz",
            # Very common short sequences
            "123456", "654321", "abcdef", "fedcba"
        ]

        password_lower = password.lower()
        return any(seq in password_lower for seq in problematic_sequences)
    
    def _has_repeated_chars(self, password: str) -> bool:
        """Check for excessive repeated characters."""
        for i in range(len(password) - 2):
            if password[i] == password[i+1] == password[i+2]:
                return True
        return False
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    async def check_password_history(self, db: AsyncSession, user_id: str, new_password: str) -> bool:
        """
        Check if password was used recently.
        Returns True if password is acceptable (not in recent history).
        """
        # This would require a password history table
        # For now, we'll implement basic check against current password
        user = await db.execute(select(User).filter(User.id == user_id))
        user = user.scalar_one_or_none()
        
        if user and self.verify_password(new_password, user.password_hash):
            return False  # Same as current password
        
        return True
    
    async def generate_reset_token(self, db: AsyncSession, user_id: str, ip_address: str = None) -> str:
        """Generate secure password reset token."""
        # Generate cryptographically secure token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Set expiration (15 minutes)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        # Store token in database
        reset_token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address
        )
        
        db.add(reset_token)
        await db.commit()
        
        return token
    
    async def verify_reset_token(self, db: AsyncSession, token: str) -> Optional[str]:
        """
        Verify password reset token and return user_id if valid.
        Returns None if token is invalid or expired.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        result = await db.execute(
            select(PasswordResetToken).filter(
                and_(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.expires_at > datetime.utcnow(),
                    PasswordResetToken.used_at.is_(None)
                )
            )
        )
        
        reset_token = result.scalar_one_or_none()
        if not reset_token:
            return None
        
        return str(reset_token.user_id)
    
    async def mark_token_used(self, db: AsyncSession, token: str) -> bool:
        """Mark reset token as used."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        result = await db.execute(
            select(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash)
        )
        
        reset_token = result.scalar_one_or_none()
        if reset_token:
            reset_token.used_at = datetime.utcnow()
            await db.commit()
            return True
        
        return False
    
    async def cleanup_expired_tokens(self, db: AsyncSession) -> int:
        """Clean up expired reset tokens."""
        from sqlalchemy import delete
        
        result = await db.execute(
            delete(PasswordResetToken).filter(
                PasswordResetToken.expires_at < datetime.utcnow()
            )
        )
        
        await db.commit()
        return result.rowcount


# Global password service instance
password_service = PasswordService()
