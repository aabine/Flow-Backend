"""
Enhanced authentication service with comprehensive security features.
Implements MFA, brute force protection, session management, and secure password policies.
"""

import asyncio
import secrets
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import redis
import logging
import hashlib
import hmac
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.security.auth import jwt_manager, password_manager, SecurityConfig
from shared.security.encryption import encryption_manager, data_masking
from shared.models import UserRole
from app.models.user import User, UserProfile, LoginAttempt, UserSession, MFADevice
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """Enhanced authentication service with security features."""
    
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        self.max_login_attempts = SecurityConfig.MAX_LOGIN_ATTEMPTS
        self.lockout_duration = SecurityConfig.LOGIN_LOCKOUT_DURATION_MINUTES
    
    async def register_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        role: UserRole,
        user_data: Dict[str, Any],
        ip_address: str = None
    ) -> Tuple[User, str]:
        """Register a new user with enhanced security validation."""
        
        # Validate password strength
        password_validation = password_manager.validate_password_strength(password)
        if not password_validation["is_valid"]:
            raise ValueError(f"Password validation failed: {', '.join(password_validation['errors'])}")
        
        # Check if user already exists
        existing_user = await self._get_user_by_email(db, email)
        if existing_user:
            # Log potential account enumeration attempt
            await self._log_security_event(
                "registration_attempt_existing_email",
                None,
                {"email": data_masking.mask_email(email), "ip_address": ip_address}
            )
            raise ValueError("User with this email already exists")
        
        # Hash password securely
        password_hash = password_manager.hash_password(password)
        
        # Encrypt sensitive user data
        encrypted_data = encryption_manager.encrypt_pii(user_data)
        
        # Create user
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            email_verified=False,
            created_at=datetime.utcnow(),
            **encrypted_data
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # Generate email verification token
        verification_token = self._generate_verification_token(user.id)
        
        # Log successful registration
        await self._log_security_event(
            "user_registered",
            str(user.id),
            {
                "email": data_masking.mask_email(email),
                "role": role.value,
                "ip_address": ip_address
            }
        )
        
        return user, verification_token
    
    async def authenticate_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None,
        require_mfa: bool = True
    ) -> Dict[str, Any]:
        """Authenticate user with brute force protection and MFA."""
        
        # Check for account lockout
        if await self._is_account_locked(email, ip_address):
            await self._log_security_event(
                "login_attempt_locked_account",
                None,
                {
                    "email": data_masking.mask_email(email),
                    "ip_address": ip_address,
                    "user_agent": user_agent
                }
            )
            raise ValueError("Account temporarily locked due to multiple failed login attempts")
        
        # Get user
        user = await self._get_user_by_email(db, email)
        if not user:
            await self._record_failed_login(email, ip_address, "user_not_found")
            raise ValueError("Invalid email or password")
        
        # Verify password
        if not password_manager.verify_password(password, user.password_hash):
            await self._record_failed_login(email, ip_address, "invalid_password", str(user.id))
            raise ValueError("Invalid email or password")
        
        # Check if user is active
        if not user.is_active:
            await self._log_security_event(
                "login_attempt_inactive_user",
                str(user.id),
                {"email": data_masking.mask_email(email), "ip_address": ip_address}
            )
            raise ValueError("Account is deactivated")
        
        # Check if email is verified
        if not user.email_verified:
            await self._log_security_event(
                "login_attempt_unverified_email",
                str(user.id),
                {"email": data_masking.mask_email(email), "ip_address": ip_address}
            )
            raise ValueError("Email address not verified")
        
        # Check for MFA requirement
        mfa_required = require_mfa and (user.role == UserRole.ADMIN or user.mfa_enabled)
        
        if mfa_required:
            # Generate MFA token
            mfa_token = jwt_manager.create_mfa_token(str(user.id), "totp")
            
            await self._log_security_event(
                "mfa_challenge_issued",
                str(user.id),
                {"email": data_masking.mask_email(email), "ip_address": ip_address}
            )
            
            return {
                "requires_mfa": True,
                "mfa_token": mfa_token,
                "user_id": str(user.id)
            }
        
        # Generate tokens and create session
        return await self._create_user_session(db, user, ip_address, user_agent)
    
    async def verify_mfa_and_complete_login(
        self,
        db: AsyncSession,
        mfa_token: str,
        mfa_code: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Dict[str, Any]:
        """Verify MFA code and complete login process."""
        
        try:
            # Verify MFA token
            payload = jwt_manager.verify_token(mfa_token, expected_type=jwt_manager.TokenType.MFA)
            user_id = payload["sub"]
            
            # Get user
            user = await self._get_user_by_id(db, user_id)
            if not user:
                raise ValueError("Invalid MFA token")
            
            # Verify MFA code
            if not await self._verify_mfa_code(db, user, mfa_code):
                await self._log_security_event(
                    "mfa_verification_failed",
                    user_id,
                    {"ip_address": ip_address, "user_agent": user_agent}
                )
                raise ValueError("Invalid MFA code")
            
            # Create session
            return await self._create_user_session(db, user, ip_address, user_agent)
            
        except Exception as e:
            logger.error(f"MFA verification error: {str(e)}")
            raise ValueError("MFA verification failed")
    
    async def setup_mfa(self, db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """Set up MFA for a user."""
        
        user = await self._get_user_by_id(db, user_id)
        if not user:
            raise ValueError("User not found")
        
        # Generate secret key
        secret = pyotp.random_base32()
        
        # Create TOTP URI
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="Oxygen Supply Platform"
        )
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        qr_code_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        # Store encrypted secret temporarily (user needs to verify setup)
        encrypted_secret = encryption_manager.encrypt_field(secret, "mfa_secret")
        
        # Store in Redis temporarily (expires in 10 minutes)
        temp_key = f"mfa_setup:{user_id}"
        self.redis_client.setex(temp_key, 600, encrypted_secret)
        
        await self._log_security_event(
            "mfa_setup_initiated",
            user_id,
            {"email": data_masking.mask_email(user.email)}
        )
        
        return {
            "secret": secret,
            "qr_code": f"data:image/png;base64,{qr_code_base64}",
            "manual_entry_key": secret
        }
    
    async def verify_mfa_setup(
        self,
        db: AsyncSession,
        user_id: str,
        verification_code: str
    ) -> bool:
        """Verify MFA setup with user-provided code."""
        
        # Get temporary secret
        temp_key = f"mfa_setup:{user_id}"
        encrypted_secret = self.redis_client.get(temp_key)
        
        if not encrypted_secret:
            raise ValueError("MFA setup session expired")
        
        secret = encryption_manager.decrypt_field(encrypted_secret, "mfa_secret")
        
        # Verify code
        totp = pyotp.TOTP(secret)
        if not totp.verify(verification_code, valid_window=1):
            raise ValueError("Invalid verification code")
        
        # Save MFA device
        user = await self._get_user_by_id(db, user_id)
        if not user:
            raise ValueError("User not found")
        
        # Encrypt and store secret
        encrypted_secret_permanent = encryption_manager.encrypt_field(secret, "mfa_secret")
        
        mfa_device = MFADevice(
            user_id=user.id,
            device_type="totp",
            secret_key=encrypted_secret_permanent,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(mfa_device)
        
        # Enable MFA for user
        user.mfa_enabled = True
        await db.commit()
        
        # Clean up temporary data
        self.redis_client.delete(temp_key)
        
        await self._log_security_event(
            "mfa_enabled",
            user_id,
            {"email": data_masking.mask_email(user.email)}
        )
        
        return True
    
    async def logout_user(self, db: AsyncSession, session_id: str, user_id: str) -> bool:
        """Securely logout user and invalidate session."""
        
        try:
            # Get session
            session = await db.execute(
                select(UserSession).where(
                    and_(
                        UserSession.id == session_id,
                        UserSession.user_id == user_id,
                        UserSession.is_active == True
                    )
                )
            )
            session = session.scalar_one_or_none()
            
            if session:
                # Deactivate session
                session.is_active = False
                session.logged_out_at = datetime.utcnow()
                await db.commit()
                
                # Add to token blacklist
                self.redis_client.setex(
                    f"blacklist:{session.access_token_jti}",
                    SecurityConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "revoked"
                )
                
                await self._log_security_event(
                    "user_logged_out",
                    user_id,
                    {"session_id": session_id}
                )
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return False

    async def _get_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email address."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _is_account_locked(self, email: str, ip_address: str) -> bool:
        """Check if account or IP is locked due to failed login attempts."""

        # Check account-based lockout
        account_key = f"login_attempts:email:{email}"
        account_attempts = self.redis_client.get(account_key)

        if account_attempts and int(account_attempts) >= self.max_login_attempts:
            return True

        # Check IP-based lockout
        if ip_address:
            ip_key = f"login_attempts:ip:{ip_address}"
            ip_attempts = self.redis_client.get(ip_key)

            if ip_attempts and int(ip_attempts) >= self.max_login_attempts * 2:  # Higher threshold for IP
                return True

        return False

    async def _record_failed_login(
        self,
        email: str,
        ip_address: str,
        reason: str,
        user_id: str = None
    ):
        """Record failed login attempt and implement lockout."""

        # Increment account-based counter
        account_key = f"login_attempts:email:{email}"
        account_attempts = self.redis_client.incr(account_key)
        self.redis_client.expire(account_key, self.lockout_duration * 60)

        # Increment IP-based counter
        if ip_address:
            ip_key = f"login_attempts:ip:{ip_address}"
            ip_attempts = self.redis_client.incr(ip_key)
            self.redis_client.expire(ip_key, self.lockout_duration * 60)

        # Log security event
        await self._log_security_event(
            "login_failed",
            user_id,
            {
                "email": data_masking.mask_email(email),
                "ip_address": ip_address,
                "reason": reason,
                "account_attempts": account_attempts,
                "ip_attempts": ip_attempts if ip_address else 0
            }
        )

    async def _create_user_session(
        self,
        db: AsyncSession,
        user: User,
        ip_address: str = None,
        user_agent: str = None
    ) -> Dict[str, Any]:
        """Create user session and generate tokens."""

        # Generate tokens
        access_token = jwt_manager.create_access_token(
            user_id=str(user.id),
            role=user.role.value,
            permissions=[]  # Add user permissions here
        )

        # Extract token ID for session tracking
        access_payload = jwt_manager.verify_token(access_token)
        access_token_jti = access_payload["jti"]

        refresh_token = jwt_manager.create_refresh_token(
            user_id=str(user.id),
            access_token_jti=access_token_jti
        )

        # Create session record
        session = UserSession(
            user_id=user.id,
            access_token_jti=access_token_jti,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=SecurityConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
            is_active=True
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        # Clear failed login attempts
        if user.email:
            self.redis_client.delete(f"login_attempts:email:{user.email}")
        if ip_address:
            self.redis_client.delete(f"login_attempts:ip:{ip_address}")

        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()

        await self._log_security_event(
            "user_logged_in",
            str(user.id),
            {
                "email": data_masking.mask_email(user.email),
                "ip_address": ip_address,
                "session_id": str(session.id)
            }
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": SecurityConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role.value,
                "mfa_enabled": user.mfa_enabled
            },
            "session_id": str(session.id)
        }

    async def _verify_mfa_code(self, db: AsyncSession, user: User, code: str) -> bool:
        """Verify MFA code for user."""

        # Get user's MFA device
        result = await db.execute(
            select(MFADevice).where(
                and_(
                    MFADevice.user_id == user.id,
                    MFADevice.is_active == True
                )
            )
        )
        mfa_device = result.scalar_one_or_none()

        if not mfa_device:
            return False

        # Decrypt secret
        secret = encryption_manager.decrypt_field(mfa_device.secret_key, "mfa_secret")

        # Verify TOTP code
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    def _generate_verification_token(self, user_id: str) -> str:
        """Generate email verification token."""
        return jwt_manager.create_access_token(
            user_id=str(user_id),
            role="verification",
            additional_claims={"type": "email_verification"}
        )

    async def _log_security_event(
        self,
        event_type: str,
        user_id: Optional[str],
        details: Dict[str, Any]
    ):
        """Log security events for monitoring."""

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "details": details
        }

        # Log to application logger
        if event_type in ["login_failed", "mfa_verification_failed", "registration_attempt_existing_email"]:
            logger.warning(f"Security Event: {event}")
        else:
            logger.info(f"Security Event: {event}")

        # Store in Redis for real-time monitoring (optional)
        event_key = f"security_event:{datetime.utcnow().timestamp()}"
        self.redis_client.setex(event_key, 3600, str(event))  # Keep for 1 hour
