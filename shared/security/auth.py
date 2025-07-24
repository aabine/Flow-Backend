"""
Shared authentication and authorization utilities for the Oxygen Supply Platform.
Implements JWT token validation, role-based access control, and security utilities.
"""

import jwt
import bcrypt
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from enum import Enum
import re
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

logger = logging.getLogger(__name__)


class SecurityConfig:
    """Security configuration constants."""
    
    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
    
    # Password Configuration
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGITS = True
    PASSWORD_REQUIRE_SPECIAL = True
    PASSWORD_SALT_ROUNDS = 12
    
    # Rate Limiting
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_LOCKOUT_DURATION_MINUTES = 15
    API_RATE_LIMIT_PER_MINUTE = 60
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    
    # Security Headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
    }


class TokenType(Enum):
    """Token types for JWT tokens."""
    ACCESS = "access"
    REFRESH = "refresh"
    MFA = "mfa"
    RESET = "reset"


class JWTManager:
    """JWT token management with enhanced security."""
    
    def __init__(self, secret_key: str = None, algorithm: str = None):
        self.secret_key = secret_key or SecurityConfig.JWT_SECRET_KEY
        self.algorithm = algorithm or SecurityConfig.JWT_ALGORITHM
        self.fernet = Fernet(SecurityConfig.ENCRYPTION_KEY.encode())
    
    def create_access_token(
        self, 
        user_id: str, 
        role: str, 
        permissions: List[str] = None,
        additional_claims: Dict[str, Any] = None
    ) -> str:
        """Create a secure access token."""
        
        now = datetime.utcnow()
        expire = now + timedelta(minutes=SecurityConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "sub": user_id,
            "role": role,
            "permissions": permissions or [],
            "type": TokenType.ACCESS.value,
            "iat": now,
            "exp": expire,
            "jti": secrets.token_urlsafe(16),  # JWT ID for token revocation
            "iss": "oxygen-platform",
            "aud": "oxygen-platform-api"
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: str, access_token_jti: str) -> str:
        """Create a refresh token linked to an access token."""
        
        now = datetime.utcnow()
        expire = now + timedelta(days=SecurityConfig.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": user_id,
            "type": TokenType.REFRESH.value,
            "iat": now,
            "exp": expire,
            "jti": secrets.token_urlsafe(16),
            "access_jti": access_token_jti,
            "iss": "oxygen-platform",
            "aud": "oxygen-platform-api"
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_mfa_token(self, user_id: str, mfa_method: str) -> str:
        """Create a temporary MFA token."""
        
        now = datetime.utcnow()
        expire = now + timedelta(minutes=5)  # Short-lived MFA token
        
        payload = {
            "sub": user_id,
            "type": TokenType.MFA.value,
            "mfa_method": mfa_method,
            "iat": now,
            "exp": expire,
            "jti": secrets.token_urlsafe(16),
            "iss": "oxygen-platform",
            "aud": "oxygen-platform-api"
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str, expected_type: TokenType = None) -> Dict[str, Any]:
        """Verify and decode a JWT token with enhanced validation."""
        
        try:
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                audience="oxygen-platform-api",
                issuer="oxygen-platform"
            )
            
            # Verify token type if specified
            if expected_type and payload.get("type") != expected_type.value:
                raise jwt.InvalidTokenError(f"Invalid token type. Expected {expected_type.value}")
            
            # Check if token is expired
            if datetime.utcnow() > datetime.fromtimestamp(payload["exp"]):
                raise jwt.ExpiredSignatureError("Token has expired")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired token attempted: {token[:20]}...")
            raise
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token attempted: {token[:20]}... - {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            raise jwt.InvalidTokenError("Token verification failed")
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data for storage."""
        return self.fernet.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        return self.fernet.decrypt(encrypted_data.encode()).decode()


class PasswordManager:
    """Secure password management utilities."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt with salt."""
        salt = bcrypt.gensalt(rounds=SecurityConfig.PASSWORD_SALT_ROUNDS)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {str(e)}")
            return False
    
    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """Validate password strength according to security policy."""
        
        errors = []
        
        if len(password) < SecurityConfig.PASSWORD_MIN_LENGTH:
            errors.append(f"Password must be at least {SecurityConfig.PASSWORD_MIN_LENGTH} characters long")
        
        if SecurityConfig.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if SecurityConfig.PASSWORD_REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if SecurityConfig.PASSWORD_REQUIRE_DIGITS and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if SecurityConfig.PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        
        # Check for common weak passwords
        weak_patterns = [
            r'password',
            r'123456',
            r'qwerty',
            r'admin',
            r'letmein'
        ]
        
        for pattern in weak_patterns:
            if re.search(pattern, password.lower()):
                errors.append("Password contains common weak patterns")
                break
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "strength_score": max(0, 100 - (len(errors) * 20))
        }
    
    @staticmethod
    def generate_secure_password(length: int = 16) -> str:
        """Generate a cryptographically secure password."""
        import string
        
        characters = (
            string.ascii_lowercase + 
            string.ascii_uppercase + 
            string.digits + 
            "!@#$%^&*"
        )
        
        password = ''.join(secrets.choice(characters) for _ in range(length))
        
        # Ensure password meets requirements
        validation = PasswordManager.validate_password_strength(password)
        if not validation["is_valid"]:
            return PasswordManager.generate_secure_password(length)
        
        return password


class SecurityValidator:
    """Input validation and sanitization utilities."""
    
    @staticmethod
    def sanitize_input(input_string: str, max_length: int = 1000) -> str:
        """Sanitize user input to prevent injection attacks."""
        
        if not isinstance(input_string, str):
            return ""
        
        # Remove null bytes
        sanitized = input_string.replace('\x00', '')
        
        # Limit length
        sanitized = sanitized[:max_length]
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\t']
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return sanitized.strip()
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email)) and len(email) <= 254
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format (Nigerian format)."""
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        
        # Check Nigerian phone number patterns
        patterns = [
            r'^234[789]\d{9}$',  # +234 format
            r'^0[789]\d{9}$',    # 0 prefix format
            r'^[789]\d{9}$'      # Without prefix
        ]
        
        return any(re.match(pattern, digits_only) for pattern in patterns)
    
    @staticmethod
    def validate_sql_injection(query_string: str) -> bool:
        """Check for potential SQL injection patterns."""
        
        dangerous_patterns = [
            r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)',
            r'(--|#|/\*|\*/)',
            r'(\bOR\b.*=.*\bOR\b)',
            r'(\bAND\b.*=.*\bAND\b)',
            r'(\'.*\'|".*")',
            r'(\bxp_|\bsp_)',
            r'(\bSCRIPT\b|\bJAVASCRIPT\b)'
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, query_string, re.IGNORECASE):
                return False
        
        return True


# Global instances
jwt_manager = JWTManager()
password_manager = PasswordManager()
security_validator = SecurityValidator()
