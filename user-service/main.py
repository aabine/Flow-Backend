from fastapi import FastAPI, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.security import create_access_token, verify_token, get_password_hash, verify_password
from app.core.database import get_db
from app.models.user import User, UserProfile, VendorProfile, HospitalProfile
from app.schemas.user import (UserCreate, UserLogin, UserResponse, TokenResponse, UserUpdate,
                             VendorProfileCreate, VendorProfileResponse, HospitalProfileCreate,
                             PasswordChangeRequest, PasswordResetRequest, PasswordResetConfirm, PasswordValidationResponse,
                             LoginWithRememberMe, RefreshTokenRequest, TokenRefreshResponse, EnhancedTokenResponse, UserSessionResponse,
                             EmailVerificationRequest, EmailVerificationConfirm,
                             MFASetupRequest, MFASetupResponse, MFAVerificationRequest, MFALoginRequest,
                             MFADisableRequest, MFADeviceResponse, BackupCodesResponse,
                             SessionInfoResponse, ActiveSessionsResponse,
                             APIKeyCreateRequest, APIKeyResponse, APIKeyCreateResponse,
                             OAuthAuthURLRequest, OAuthAuthURLResponse, OAuthCallbackRequest, OAuthLoginResponse)
from app.services.user_service import UserService
from app.services.password_service import password_service
from app.services.jwt_service import jwt_service
from app.services.email_service import email_service
from app.services.mfa_service import mfa_service
from app.services.rate_limit_service import rate_limit_service
from app.services.security_event_service import security_event_service, SecurityEventType
from app.services.file_upload_service import file_upload_service
from app.services.gdpr_service import gdpr_service
from app.services.api_key_service import api_key_service, APIKeyPermission
from app.services.oauth_service import oauth_service, OAuthProvider
from app.middleware.rate_limit_middleware import (RateLimitMiddleware, LoginRateLimitMiddleware,
                                                 PasswordResetRateLimitMiddleware, EmailVerificationRateLimitMiddleware)
from app.middleware.api_key_middleware import api_key_auth, service_auth, user_read_auth, admin_auth
from app.utils.device_detection import get_device_info, format_session_info
from shared.models import UserRole, APIResponse

app = FastAPI(
    title="User Service",
    description="User management and authentication service",
    version="1.0.0"
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
user_service = UserService()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "User Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/auth/register", response_model=APIResponse)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user with email verification."""
    try:
        # Check if user already exists
        existing_user = await user_service.get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        # Validate password strength
        validation = password_service.validate_password_strength(user_data.password)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password validation failed: {', '.join(validation['errors'])}"
            )

        # Create new user
        user = await user_service.create_user(db, user_data)

        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")
        user_name = user_data.first_name

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.ACCOUNT_CREATED, str(user.id), ip_address, user_agent,
            {"email": user.email, "role": user.role.value}
        )

        # Send verification email
        email_sent = await email_service.send_verification_email(
            db=db,
            user_id=str(user.id),
            email=user.email,
            user_name=user_name
        )

        if email_sent:
            await security_event_service.log_security_event(
                db, SecurityEventType.EMAIL_VERIFICATION_SENT, str(user.id), ip_address, user_agent
            )

        message = "User registered successfully"
        if email_sent:
            message += ". Please check your email to verify your account"
        else:
            message += ". Email verification will be sent shortly"

        return APIResponse(
            success=True,
            message=message,
            data={
                "user_id": str(user.id),
                "email": user.email,
                "role": user.role.value,
                "email_verification_sent": email_sent
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@app.post("/auth/login", response_model=EnhancedTokenResponse)
async def login(
    login_data: LoginWithRememberMe,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """User login with refresh token support and brute force protection."""
    try:
        # Check rate limits
        await LoginRateLimitMiddleware.check_login_rate_limit(request)

        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")

        # Check account lockout
        is_locked, locked_until = await rate_limit_service.check_account_lockout(db, login_data.email)
        if is_locked:
            # Record failed attempt
            await rate_limit_service.record_login_attempt(
                db, login_data.email, ip_address, user_agent, False, "account_locked"
            )

            # Increment rate limit counters
            await rate_limit_service.increment_login_attempts(f"ip:{ip_address}")
            await rate_limit_service.increment_login_attempts(f"email:{login_data.email}")

            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account is temporarily locked until {locked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                headers={"Retry-After": "1800"}  # 30 minutes
            )

        # Authenticate user
        user = await user_service.authenticate_user(db, login_data.email, login_data.password)
        if not user:
            # Record failed attempt
            await rate_limit_service.record_login_attempt(
                db, login_data.email, ip_address, user_agent, False, "invalid_credentials"
            )

            # Log security event
            await security_event_service.log_security_event(
                db, SecurityEventType.LOGIN_FAILED, None, ip_address, user_agent,
                {"email": login_data.email, "reason": "invalid_credentials"}
            )

            # Increment rate limit counters
            await rate_limit_service.increment_login_attempts(f"ip:{ip_address}")
            await rate_limit_service.increment_login_attempts(f"email:{login_data.email}")

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not user.is_active:
            # Record failed attempt
            await rate_limit_service.record_login_attempt(
                db, login_data.email, ip_address, user_agent, False, "account_inactive", str(user.id)
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )

        # Check if email is verified
        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your email address before logging in"
            )

        # Check if MFA is required
        if user.mfa_enabled:
            # Create temporary MFA token
            from jose import jwt
            from datetime import timedelta

            mfa_expire = datetime.utcnow() + timedelta(minutes=5)  # 5 minute expiry
            mfa_payload = {
                "user_id": str(user.id),
                "type": "mfa",
                "exp": mfa_expire,
                "iat": datetime.utcnow()
            }

            mfa_token = jwt.encode(mfa_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

            return {
                "requires_mfa": True,
                "mfa_token": mfa_token,
                "message": "MFA verification required"
            }

        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")

        # Create session with tokens
        session_data = await jwt_service.create_user_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            remember_me=login_data.remember_me
        )

        # Update last login
        await user_service.update_last_login(db, user.id)

        # Record successful login
        await rate_limit_service.record_login_attempt(
            db, login_data.email, ip_address, user_agent, True, None, str(user.id)
        )

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.LOGIN_SUCCESS, str(user.id), ip_address, user_agent,
            {"remember_me": login_data.remember_me}
        )

        # Reset failed attempts on successful login
        await rate_limit_service.reset_failed_attempts(db, login_data.email)

        return EnhancedTokenResponse(
            access_token=session_data["access_token"],
            refresh_token=session_data["refresh_token"],
            token_type=session_data["token_type"],
            expires_in=session_data["expires_in"],
            session_id=session_data["session_id"],
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@app.post("/auth/verify-token")
async def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token."""
    try:
        payload = verify_token(credentials.credentials)
        return {
            "valid": True,
            "user_id": payload.get("user_id"),
            "email": payload.get("sub"),
            "role": payload.get("role")
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


@app.get("/profile", response_model=UserResponse)
async def get_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user profile."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )


@app.put("/profile", response_model=APIResponse)
async def update_profile(
    user_update: UserUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        
        user = await user_service.update_user(db, user_id, user_update)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return APIResponse(
            success=True,
            message="Profile updated successfully",
            data={
                "user_id": str(user.id),
                "email": user.email
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user by ID (admin only)."""
    try:
        payload = verify_token(credentials.credentials)
        if payload.get("role") != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )


@app.post("/users/{user_id}/deactivate", response_model=APIResponse)
async def deactivate_user(
    user_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate user (admin only)."""
    try:
        payload = verify_token(credentials.credentials)
        if payload.get("role") != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        success = await user_service.deactivate_user(db, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return APIResponse(
            success=True,
            message="User deactivated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate user: {str(e)}"
        )


@app.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token."""
    try:
        ip_address = request.client.host

        token_data = await jwt_service.refresh_access_token(
            db=db,
            refresh_token=refresh_data.refresh_token,
            ip_address=ip_address
        )

        return TokenRefreshResponse(**token_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@app.post("/auth/logout", response_model=APIResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Logout current session."""
    try:
        payload = verify_token(credentials.credentials)
        jti = payload.get("jti")

        # Find and revoke session by access token JTI
        from sqlalchemy import update
        from app.models.user import UserSession
        from datetime import datetime

        stmt = update(UserSession).where(
            UserSession.access_token_jti == jti
        ).values(
            is_active=False,
            logged_out_at=datetime.utcnow()
        )

        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount > 0:
            return APIResponse(
                success=True,
                message="Logged out successfully"
            )
        else:
            return APIResponse(
                success=True,
                message="Session already expired"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}"
        )


@app.post("/auth/logout-all", response_model=APIResponse)
async def logout_all_devices(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Logout from all devices."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        revoked_count = await jwt_service.revoke_all_user_sessions(db, user_id)

        return APIResponse(
            success=True,
            message=f"Logged out from {revoked_count} devices"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout all failed: {str(e)}"
        )


@app.get("/auth/sessions", response_model=ActiveSessionsResponse)
async def get_user_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user's active sessions with device information."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        current_jti = payload.get("jti")

        # Get sessions from database with full details
        from sqlalchemy import select
        from app.models.user import UserSession
        import uuid

        result = await db.execute(
            select(UserSession).filter(
                and_(
                    UserSession.user_id == uuid.UUID(user_id),
                    UserSession.is_active == True
                )
            ).order_by(UserSession.last_activity.desc())
        )

        sessions = result.scalars().all()
        current_session_id = None

        formatted_sessions = []
        for session in sessions:
            is_current = session.access_token_jti == current_jti
            if is_current:
                current_session_id = str(session.id)

            # Get device information
            device_info = get_device_info(session.user_agent or "")

            session_info = SessionInfoResponse(
                id=str(session.id),
                ip_address=session.ip_address,
                user_agent=session.user_agent,
                created_at=session.created_at,
                last_activity=session.last_activity,
                expires_at=session.expires_at,
                is_current=is_current,
                device_type=device_info['description']
            )

            formatted_sessions.append(session_info)

        return ActiveSessionsResponse(
            sessions=formatted_sessions,
            total_count=len(formatted_sessions),
            current_session_id=current_session_id
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sessions: {str(e)}"
        )


@app.delete("/auth/sessions/{session_id}", response_model=APIResponse)
async def revoke_session(
    session_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Revoke a specific session."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Verify session belongs to user
        from sqlalchemy import select, and_
        from app.models.user import UserSession
        import uuid

        result = await db.execute(
            select(UserSession).filter(
                and_(
                    UserSession.id == uuid.UUID(session_id),
                    UserSession.user_id == uuid.UUID(user_id)
                )
            )
        )

        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        success = await jwt_service.revoke_session(db, session_id)

        if success:
            return APIResponse(
                success=True,
                message="Session revoked successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to revoke session"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke session: {str(e)}"
        )


# Multi-Factor Authentication (MFA) Endpoints
@app.post("/auth/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    setup_data: MFASetupRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Setup MFA for current user."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        setup_info = await mfa_service.setup_mfa_device(
            db=db,
            user_id=user_id,
            device_name=setup_data.device_name,
            device_type=setup_data.device_type
        )

        return MFASetupResponse(**setup_info)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MFA setup failed: {str(e)}"
        )


@app.post("/auth/mfa/verify-setup", response_model=APIResponse)
async def verify_mfa_setup(
    verification_data: MFAVerificationRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Verify and activate MFA setup."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        success = await mfa_service.verify_and_activate_mfa(
            db=db,
            user_id=user_id,
            device_id=verification_data.device_id,
            verification_code=verification_data.verification_code
        )

        if success:
            return APIResponse(
                success=True,
                message="MFA activated successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA activation failed"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MFA verification failed: {str(e)}"
        )


@app.post("/auth/mfa/verify", response_model=EnhancedTokenResponse)
async def verify_mfa_login(
    mfa_data: MFALoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Complete login with MFA verification."""
    try:
        # Verify MFA token (temporary token from login)
        payload = verify_token(mfa_data.mfa_token)

        if payload.get("type") != "mfa":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid MFA token"
            )

        user_id = payload.get("user_id")

        # Verify MFA code
        mfa_valid = await mfa_service.verify_mfa_code(
            db=db,
            user_id=user_id,
            code=mfa_data.verification_code
        )

        if not mfa_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code"
            )

        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Create session with tokens
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")

        session_data = await jwt_service.create_user_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            remember_me=False
        )

        # Update last login
        await user_service.update_last_login(db, user.id)

        return EnhancedTokenResponse(
            access_token=session_data["access_token"],
            refresh_token=session_data["refresh_token"],
            token_type=session_data["token_type"],
            expires_in=session_data["expires_in"],
            session_id=session_data["session_id"],
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MFA verification failed: {str(e)}"
        )


@app.post("/auth/mfa/disable", response_model=APIResponse)
async def disable_mfa(
    disable_data: MFADisableRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Disable MFA for current user."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        success = await mfa_service.disable_mfa(
            db=db,
            user_id=user_id,
            verification_code=disable_data.verification_code
        )

        if success:
            return APIResponse(
                success=True,
                message="MFA disabled successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA disable failed"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MFA disable failed: {str(e)}"
        )


@app.get("/auth/mfa/devices", response_model=APIResponse)
async def get_mfa_devices(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user's MFA devices."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        devices = await mfa_service.get_user_mfa_devices(db, user_id)

        return APIResponse(
            success=True,
            message="MFA devices retrieved successfully",
            data={"devices": devices}
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get MFA devices: {str(e)}"
        )


@app.post("/auth/mfa/backup-codes/regenerate", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    disable_data: MFADisableRequest,  # Reuse for verification code
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate backup codes."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        backup_codes = await mfa_service.regenerate_backup_codes(
            db=db,
            user_id=user_id,
            verification_code=disable_data.verification_code
        )

        return BackupCodesResponse(backup_codes=backup_codes)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup code regeneration failed: {str(e)}"
        )


# Email Verification Endpoints
@app.post("/auth/send-verification-email", response_model=APIResponse)
async def send_verification_email(
    request_data: EmailVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Send email verification email."""
    try:
        # Check rate limits
        await EmailVerificationRateLimitMiddleware.check_email_verification_rate_limit(request)

        # Increment rate limit counter
        ip_address = request.client.host
        await rate_limit_service.increment_email_verification_attempts(f"ip:{ip_address}")
        await rate_limit_service.increment_email_verification_attempts(f"email:{request_data.email}")
        # Get user by email
        user = await user_service.get_user_by_email(db, request_data.email)

        if not user:
            # Don't reveal if email exists
            return APIResponse(
                success=True,
                message="If the email exists, a verification email has been sent"
            )

        if user.email_verified:
            return APIResponse(
                success=True,
                message="Email is already verified"
            )

        # Get user profile for name
        from sqlalchemy import select
        from app.models.user import UserProfile

        profile_result = await db.execute(
            select(UserProfile).filter(UserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        user_name = None
        if profile and profile.first_name:
            user_name = profile.first_name

        # Send verification email
        ip_address = request.client.host
        success = await email_service.send_verification_email(
            db=db,
            user_id=str(user.id),
            email=user.email,
            user_name=user_name
        )

        if success:
            return APIResponse(
                success=True,
                message="Verification email sent successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send verification email: {str(e)}"
        )


@app.post("/auth/verify-email", response_model=APIResponse)
async def verify_email(
    verification_data: EmailVerificationConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Verify email address with token."""
    try:
        # Verify token
        user_id = await email_service.verify_email_token(db, verification_data.token)

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )

        # Update user email_verified status
        from sqlalchemy import update
        import uuid

        stmt = update(User).where(
            User.id == uuid.UUID(user_id)
        ).values(email_verified=True)

        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount > 0:
            # Mark token as used
            await email_service.mark_email_token_used(db, verification_data.token)

            return APIResponse(
                success=True,
                message="Email verified successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email verification failed: {str(e)}"
        )


@app.get("/auth/verification-status", response_model=APIResponse)
async def get_verification_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's email verification status."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return APIResponse(
            success=True,
            message="Verification status retrieved",
            data={
                "email_verified": user.email_verified,
                "email": user.email
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get verification status: {str(e)}"
        )


# Password Management Endpoints
@app.post("/auth/change-password", response_model=APIResponse)
async def change_password(
    password_data: PasswordChangeRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Change user password."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Validate password confirmation
        if password_data.new_password != password_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password confirmation does not match"
            )

        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify current password
        if not password_service.verify_password(password_data.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Validate new password strength
        validation = password_service.validate_password_strength(password_data.new_password)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password validation failed: {', '.join(validation['errors'])}"
            )

        # Check password history
        if not await password_service.check_password_history(db, user_id, password_data.new_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reuse recent passwords"
            )

        # Update password
        new_password_hash = password_service.hash_password(password_data.new_password)
        from sqlalchemy import update
        from datetime import datetime

        stmt = update(User).where(User.id == user.id).values(
            password_hash=new_password_hash,
            password_changed_at=datetime.utcnow()
        )
        await db.execute(stmt)
        await db.commit()

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.PASSWORD_CHANGED, user_id, None, None
        )

        return APIResponse(
            success=True,
            message="Password changed successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )


@app.post("/auth/forgot-password", response_model=APIResponse)
async def forgot_password(
    request_data: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Request password reset."""
    try:
        # Check rate limits
        await PasswordResetRateLimitMiddleware.check_password_reset_rate_limit(request)

        # Increment rate limit counter
        ip_address = request.client.host
        await rate_limit_service.increment_password_reset_attempts(f"ip:{ip_address}")
        await rate_limit_service.increment_password_reset_attempts(f"email:{request_data.email}")
        # Get user by email
        user = await user_service.get_user_by_email(db, request_data.email)

        # Always return success to prevent email enumeration
        if not user:
            return APIResponse(
                success=True,
                message="If the email exists, a password reset link has been sent"
            )

        # Generate reset token
        ip_address = request.client.host
        reset_token = await password_service.generate_reset_token(db, str(user.id), ip_address)

        # Get user profile for name
        from sqlalchemy import select
        from app.models.user import UserProfile

        profile_result = await db.execute(
            select(UserProfile).filter(UserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        user_name = None
        if profile and profile.first_name:
            user_name = profile.first_name

        # Send password reset email
        email_sent = await email_service.send_password_reset_email(
            email=user.email,
            token=reset_token,
            user_name=user_name
        )

        # Always return success to prevent email enumeration
        return APIResponse(
            success=True,
            message="If the email exists, a password reset link has been sent"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process password reset request: {str(e)}"
        )


@app.post("/auth/reset-password", response_model=APIResponse)
async def reset_password(
    reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token."""
    try:
        # Validate password confirmation
        if reset_data.new_password != reset_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password confirmation does not match"
            )

        # Verify reset token
        user_id = await password_service.verify_reset_token(db, reset_data.token)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )

        # Validate new password strength
        validation = password_service.validate_password_strength(reset_data.new_password)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password validation failed: {', '.join(validation['errors'])}"
            )

        # Update password
        new_password_hash = password_service.hash_password(reset_data.new_password)
        from sqlalchemy import update
        from datetime import datetime

        stmt = update(User).where(User.id == user_id).values(
            password_hash=new_password_hash,
            password_changed_at=datetime.utcnow()
        )
        await db.execute(stmt)
        await db.commit()

        # Mark token as used
        await password_service.mark_token_used(db, reset_data.token)

        return APIResponse(
            success=True,
            message="Password reset successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset password: {str(e)}"
        )


@app.post("/auth/validate-password", response_model=PasswordValidationResponse)
async def validate_password_strength(password: str):
    """Validate password strength."""
    try:
        validation = password_service.validate_password_strength(password)
        return PasswordValidationResponse(**validation)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate password: {str(e)}"
        )


@app.get("/auth/rate-limit-status", response_model=APIResponse)
async def get_rate_limit_status(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get current rate limit status for user."""
    try:
        # Get client identifier
        ip_address = request.client.host

        # Try to get user ID from token
        user_id = None
        try:
            payload = verify_token(credentials.credentials)
            user_id = payload.get("user_id")
        except:
            pass

        # Get rate limit info for different types
        api_info = await rate_limit_service.get_rate_limit_info("api", f"user:{user_id}" if user_id else f"ip:{ip_address}")
        login_info = await rate_limit_service.get_rate_limit_info("login", f"ip:{ip_address}")

        return APIResponse(
            success=True,
            message="Rate limit status retrieved",
            data={
                "api_rate_limit": api_info,
                "login_rate_limit": login_info,
                "client_identifier": f"user:{user_id}" if user_id else f"ip:{ip_address}"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get rate limit status: {str(e)}"
        )


# Security Monitoring Endpoints
@app.get("/auth/security-events", response_model=APIResponse)
async def get_security_events(
    limit: int = Query(50, ge=1, le=100),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user's security events."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Parse event types if provided
        parsed_event_types = None
        if event_types:
            try:
                parsed_event_types = [
                    SecurityEventType(event_type.strip())
                    for event_type in event_types.split(",")
                ]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {str(e)}"
                )

        events = await security_event_service.get_user_security_events(
            db, user_id, limit, parsed_event_types
        )

        return APIResponse(
            success=True,
            message="Security events retrieved successfully",
            data={
                "events": events,
                "total": len(events)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get security events: {str(e)}"
        )


@app.get("/auth/security-summary", response_model=APIResponse)
async def get_security_summary(
    days: int = Query(30, ge=1, le=365),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get user's security summary."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        summary = await security_event_service.get_security_summary(db, user_id, days)

        return APIResponse(
            success=True,
            message="Security summary retrieved successfully",
            data=summary
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get security summary: {str(e)}"
        )


@app.post("/auth/report-suspicious", response_model=APIResponse)
async def report_suspicious_activity(
    description: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Allow users to report suspicious activity on their account."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")

        # Log the user report
        await security_event_service.log_security_event(
            db, SecurityEventType.SUSPICIOUS_ACTIVITY, user_id, ip_address, user_agent,
            {
                "type": "user_reported",
                "description": description,
                "reported_by_user": True
            }
        )

        return APIResponse(
            success=True,
            message="Suspicious activity report submitted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to report suspicious activity: {str(e)}"
        )


# Profile Management Endpoints
@app.post("/profile/upload-avatar", response_model=APIResponse)
async def upload_profile_picture(
    file: UploadFile,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Upload profile picture."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Upload file
        file_info = await file_upload_service.upload_profile_picture(user_id, file)

        # Update user profile with avatar URL
        from sqlalchemy import update
        from app.models.user import UserProfile
        import uuid

        stmt = update(UserProfile).where(
            UserProfile.user_id == uuid.UUID(user_id)
        ).values(avatar_url=file_info["url"])

        result = await db.execute(stmt)
        await db.commit()

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.PROFILE_UPDATED, user_id, None, None,
            {"action": "avatar_uploaded", "filename": file_info["filename"]}
        )

        return APIResponse(
            success=True,
            message="Profile picture uploaded successfully",
            data={
                "avatar_url": file_info["url"],
                "file_size": file_info["file_size"]
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload profile picture: {str(e)}"
        )


@app.delete("/profile/delete-account", response_model=APIResponse)
async def delete_user_account(
    confirmation: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Delete user account (GDPR right to be forgotten)."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Require explicit confirmation
        if confirmation != "DELETE_MY_ACCOUNT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account deletion requires confirmation string: 'DELETE_MY_ACCOUNT'"
            )

        # Get user
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Log security event before deletion
        await security_event_service.log_security_event(
            db, SecurityEventType.ACCOUNT_DEACTIVATED, user_id, None, None,
            {"action": "user_requested_deletion", "email": user.email}
        )

        # Deactivate account instead of hard delete (for audit trail)
        from sqlalchemy import update
        from datetime import datetime

        stmt = update(User).where(User.id == user.id).values(
            is_active=False,
            email=f"deleted_{user.id}@deleted.local",  # Anonymize email
            updated_at=datetime.utcnow()
        )
        await db.execute(stmt)

        # Revoke all sessions
        await jwt_service.revoke_all_user_sessions(db, user_id)

        await db.commit()

        return APIResponse(
            success=True,
            message="Account has been deactivated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )


@app.get("/profile/export-data", response_model=APIResponse)
async def export_user_data(
    include_security_logs: bool = Query(True),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Export user data for GDPR compliance."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")

        # Generate data export
        export_data = await gdpr_service.export_user_data(
            db, user_id, include_security_logs
        )

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.PROFILE_VIEWED, user_id, None, None,
            {"action": "data_export_requested", "include_security_logs": include_security_logs}
        )

        # Return download information
        from fastapi.responses import Response
        import base64

        # For now, return base64 encoded data
        # In production, you might want to store this temporarily and provide a download link
        encoded_data = base64.b64encode(export_data).decode()

        return APIResponse(
            success=True,
            message="Data export generated successfully",
            data={
                "export_size_bytes": len(export_data),
                "export_date": datetime.utcnow().isoformat(),
                "download_data": encoded_data,  # Base64 encoded ZIP file
                "filename": f"user_data_export_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export user data: {str(e)}"
        )


# API Key Management Endpoints
@app.post("/api-keys", response_model=APIKeyCreateResponse)
async def create_api_key(
    key_data: APIKeyCreateRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Create new API key."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        # Only admins can create API keys with admin permissions
        admin_permissions = {APIKeyPermission.ADMIN_READ.value, APIKeyPermission.ADMIN_WRITE.value, APIKeyPermission.ALL.value}
        if any(perm in admin_permissions for perm in key_data.permissions):
            if user_role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only administrators can create API keys with admin permissions"
                )

        # Get client IP
        ip_address = request.client.host

        # Create API key
        key_info = await api_key_service.create_api_key(
            db=db,
            key_name=key_data.key_name,
            permissions=key_data.permissions,
            user_id=user_id,
            expires_in_days=key_data.expires_in_days,
            created_by_ip=ip_address
        )

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.ADMIN_ACTION, user_id, ip_address, None,
            {
                "action": "api_key_created",
                "key_name": key_data.key_name,
                "permissions": key_data.permissions
            }
        )

        return APIKeyCreateResponse(**key_info)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@app.get("/api-keys", response_model=APIResponse)
async def list_api_keys(
    include_inactive: bool = Query(False),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """List user's API keys."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        # Admins can see all keys, users can only see their own
        list_user_id = None if user_role == UserRole.ADMIN else user_id

        api_keys = await api_key_service.list_api_keys(
            db, list_user_id, include_inactive
        )

        return APIResponse(
            success=True,
            message="API keys retrieved successfully",
            data={
                "api_keys": api_keys,
                "total": len(api_keys)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}"
        )


@app.delete("/api-keys/{key_id}", response_model=APIResponse)
async def revoke_api_key(
    key_id: str,
    permanent: bool = Query(False, description="Permanently delete instead of deactivate"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Revoke or delete API key."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        # Admins can revoke any key, users can only revoke their own
        revoke_user_id = None if user_role == UserRole.ADMIN else user_id

        if permanent:
            success = await api_key_service.delete_api_key(db, key_id, revoke_user_id)
            action = "deleted"
        else:
            success = await api_key_service.revoke_api_key(db, key_id, revoke_user_id)
            action = "revoked"

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found or access denied"
            )

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.ADMIN_ACTION, user_id, None, None,
            {
                "action": f"api_key_{action}",
                "key_id": key_id,
                "permanent": permanent
            }
        )

        return APIResponse(
            success=True,
            message=f"API key {action} successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {action} API key: {str(e)}"
        )


@app.post("/api-keys/{key_id}/rotate", response_model=APIKeyCreateResponse)
async def rotate_api_key(
    key_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Rotate API key (generate new key with same permissions)."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        # Admins can rotate any key, users can only rotate their own
        rotate_user_id = None if user_role == UserRole.ADMIN else user_id

        key_info = await api_key_service.rotate_api_key(db, key_id, rotate_user_id)

        if not key_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found or access denied"
            )

        # Log security event
        await security_event_service.log_security_event(
            db, SecurityEventType.ADMIN_ACTION, user_id, None, None,
            {
                "action": "api_key_rotated",
                "key_id": key_id,
                "key_name": key_info["key_name"]
            }
        )

        return APIKeyCreateResponse(**key_info)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate API key: {str(e)}"
        )


# Service-to-Service API Endpoints (Protected by API Keys)
@app.get("/internal/users/{user_id}", response_model=UserResponse)
async def get_user_for_service(
    user_id: str,
    key_info: dict = Depends(user_read_auth),
    db: AsyncSession = Depends(get_db)
):
    """Get user information for service-to-service communication."""
    try:
        user = await user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return UserResponse(
            id=str(user.id),
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user: {str(e)}"
        )


@app.get("/internal/health", response_model=APIResponse)
async def service_health_check(
    key_info: dict = Depends(service_auth)
):
    """Health check endpoint for service-to-service monitoring."""
    return APIResponse(
        success=True,
        message="User service is healthy",
        data={
            "service": "user-service",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "authenticated_as": key_info.get("key_name", "unknown")
        }
    )


# OAuth/Social Login Endpoints
@app.post("/auth/oauth/url", response_model=OAuthAuthURLResponse)
async def get_oauth_auth_url(
    oauth_request: OAuthAuthURLRequest
):
    """Get OAuth authorization URL for social login."""
    try:
        # Generate state parameter
        state = oauth_service.generate_oauth_state()

        # Get authorization URL based on provider
        if oauth_request.provider == OAuthProvider.GOOGLE:
            auth_url = oauth_service.get_google_auth_url(state, oauth_request.role)
        elif oauth_request.provider == OAuthProvider.FACEBOOK:
            auth_url = oauth_service.get_facebook_auth_url(state, oauth_request.role)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported OAuth provider"
            )

        return OAuthAuthURLResponse(
            auth_url=auth_url,
            state=state,
            provider=oauth_request.provider
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate OAuth URL: {str(e)}"
        )


@app.post("/auth/oauth/callback", response_model=OAuthLoginResponse)
async def oauth_callback(
    callback_data: OAuthCallbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle OAuth callback and complete authentication."""
    try:
        # Parse state to get role if provided
        state_parts = callback_data.state.split(":", 1)
        role = state_parts[1] if len(state_parts) > 1 else None

        # Get client info
        ip_address = request.client.host
        user_agent = request.headers.get("User-Agent")

        # Authenticate with OAuth provider
        auth_result = None
        if callback_data.provider == OAuthProvider.GOOGLE:
            auth_result = await oauth_service.authenticate_with_google(
                db, callback_data.code, role
            )
        elif callback_data.provider == OAuthProvider.FACEBOOK:
            auth_result = await oauth_service.authenticate_with_facebook(
                db, callback_data.code, role
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported OAuth provider"
            )

        if not auth_result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OAuth authentication failed"
            )

        user = auth_result["user"]
        oauth_provider = auth_result["oauth_provider"]
        oauth_user_info = auth_result["oauth_user_info"]

        # Check if this is a new user (created in the last minute)
        is_new_user = (datetime.utcnow() - user.created_at).total_seconds() < 60

        # Create session with tokens
        session_data = await jwt_service.create_user_session(
            db=db,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            remember_me=False
        )

        # Log security event
        event_type = SecurityEventType.ACCOUNT_CREATED if is_new_user else SecurityEventType.LOGIN_SUCCESS
        await security_event_service.log_security_event(
            db, event_type, str(user.id), ip_address, user_agent,
            {
                "oauth_provider": oauth_provider,
                "oauth_user_id": oauth_user_info.get("id"),
                "is_new_user": is_new_user
            }
        )

        return OAuthLoginResponse(
            access_token=session_data["access_token"],
            refresh_token=session_data["refresh_token"],
            token_type=session_data["token_type"],
            expires_in=session_data["expires_in"],
            session_id=session_data["session_id"],
            user=UserResponse(
                id=str(user.id),
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login
            ),
            oauth_provider=oauth_provider,
            is_new_user=is_new_user
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {str(e)}"
        )


@app.get("/auth/oauth/providers", response_model=APIResponse)
async def get_oauth_providers():
    """Get available OAuth providers and their configuration status."""
    try:
        from app.services.oauth_service import OAuthConfig
        config = OAuthConfig()

        providers = {
            "google": {
                "name": "Google",
                "provider_id": OAuthProvider.GOOGLE,
                "available": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET),
                "scopes": ["openid", "email", "profile"]
            },
            "facebook": {
                "name": "Facebook",
                "provider_id": OAuthProvider.FACEBOOK,
                "available": bool(config.FACEBOOK_APP_ID and config.FACEBOOK_APP_SECRET),
                "scopes": ["email", "public_profile"]
            }
        }

        return APIResponse(
            success=True,
            message="OAuth providers retrieved successfully",
            data={
                "providers": providers,
                "total_available": sum(1 for p in providers.values() if p["available"])
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get OAuth providers: {str(e)}"
        )


# Vendor Profile Management Endpoints
@app.post("/vendor-profiles", response_model=APIResponse)
async def create_vendor_profile(
    profile_data: VendorProfileCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Create vendor profile for current user."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        if user_role != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can create vendor profiles"
            )

        # Check if vendor profile already exists
        existing_profile = await user_service.get_vendor_profile(db, user_id)
        if existing_profile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vendor profile already exists"
            )

        profile = await user_service.create_vendor_profile(db, user_id, profile_data)

        return APIResponse(
            success=True,
            message="Vendor profile created successfully",
            data={"vendor_profile_id": str(profile.id)}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create vendor profile: {str(e)}"
        )


@app.get("/vendor-profiles/{user_id}", response_model=VendorProfileResponse)
async def get_vendor_profile(
    user_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor profile by user ID (for inter-service communication)."""
    try:
        payload = verify_token(credentials.credentials)
        requesting_user_id = payload.get("user_id")
        requesting_user_role = payload.get("role")

        # Allow access for:
        # 1. The vendor themselves
        # 2. Admin users
        # 3. Other services (we'll identify by role or add service authentication later)
        if requesting_user_id != user_id and requesting_user_role not in [UserRole.ADMIN, UserRole.HOSPITAL]:
            # For now, allow all authenticated users (for inter-service communication)
            # In production, implement proper service-to-service authentication
            pass

        profile = await user_service.get_vendor_profile(db, user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor profile not found"
            )

        return VendorProfileResponse(
            id=str(profile.id),
            user_id=str(profile.user_id),
            business_name=profile.business_name,
            registration_number=profile.registration_number,
            tax_identification_number=profile.tax_identification_number,
            contact_person=profile.contact_person,
            contact_phone=profile.contact_phone,
            business_address=profile.business_address,
            delivery_radius_km=profile.delivery_radius_km,
            operating_hours=profile.operating_hours,
            emergency_service=profile.emergency_service,
            minimum_order_value=profile.minimum_order_value,
            payment_terms=profile.payment_terms,
            supplier_onboarding_status=profile.supplier_onboarding_status,
            supplier_onboarding_response_time=profile.supplier_onboarding_response_time,
            created_at=profile.created_at,
            updated_at=profile.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor profile: {str(e)}"
        )


@app.get("/vendor-profiles/me", response_model=VendorProfileResponse)
async def get_my_vendor_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's vendor profile."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        if user_role != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can access vendor profiles"
            )

        profile = await user_service.get_vendor_profile(db, user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor profile not found"
            )

        return VendorProfileResponse(
            id=str(profile.id),
            user_id=str(profile.user_id),
            business_name=profile.business_name,
            registration_number=profile.registration_number,
            tax_identification_number=profile.tax_identification_number,
            contact_person=profile.contact_person,
            contact_phone=profile.contact_phone,
            business_address=profile.business_address,
            delivery_radius_km=profile.delivery_radius_km,
            operating_hours=profile.operating_hours,
            emergency_service=profile.emergency_service,
            minimum_order_value=profile.minimum_order_value,
            payment_terms=profile.payment_terms,
            supplier_onboarding_status=profile.supplier_onboarding_status,
            supplier_onboarding_response_time=profile.supplier_onboarding_response_time,
            created_at=profile.created_at,
            updated_at=profile.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get vendor profile: {str(e)}"
        )


@app.put("/vendor-profiles/me", response_model=APIResponse)
async def update_my_vendor_profile(
    profile_data: VendorProfileCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's vendor profile."""
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("user_id")
        user_role = payload.get("role")

        if user_role != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can update vendor profiles"
            )

        # Check if vendor profile exists
        existing_profile = await user_service.get_vendor_profile(db, user_id)
        if not existing_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor profile not found"
            )

        # Update vendor profile
        from sqlalchemy import update
        from app.models.user import VendorProfile
        import uuid

        stmt = update(VendorProfile).where(
            VendorProfile.user_id == uuid.UUID(user_id)
        ).values(**profile_data.dict(exclude_unset=True))

        await db.execute(stmt)
        await db.commit()

        return APIResponse(
            success=True,
            message="Vendor profile updated successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update vendor profile: {str(e)}"
        )


# Vendor Search Endpoint for Inter-Service Communication
@app.get("/vendors/search", response_model=APIResponse)
async def search_vendors(
    business_name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    emergency_service: Optional[bool] = Query(None),
    min_delivery_radius: Optional[float] = Query(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """Search vendors by criteria (for inter-service communication)."""
    try:
        payload = verify_token(credentials.credentials)

        from sqlalchemy import select, and_
        from app.models.user import VendorProfile

        # Build query conditions
        conditions = []
        if business_name:
            conditions.append(VendorProfile.business_name.ilike(f"%{business_name}%"))
        if emergency_service is not None:
            conditions.append(VendorProfile.emergency_service == emergency_service)
        if min_delivery_radius:
            conditions.append(VendorProfile.delivery_radius_km >= min_delivery_radius)

        # Execute query
        query = select(VendorProfile)
        if conditions:
            query = query.where(and_(*conditions))

        result = await db.execute(query)
        vendors = result.scalars().all()

        vendor_list = []
        for vendor in vendors:
            vendor_list.append({
                "user_id": str(vendor.user_id),
                "business_name": vendor.business_name,
                "contact_phone": vendor.contact_phone,
                "business_address": vendor.business_address,
                "delivery_radius_km": vendor.delivery_radius_km,
                "emergency_service": vendor.emergency_service,
                "minimum_order_value": vendor.minimum_order_value,
                "supplier_onboarding_status": vendor.supplier_onboarding_status.value if vendor.supplier_onboarding_status else None
            })

        return APIResponse(
            success=True,
            message="Vendors retrieved successfully",
            data={
                "vendors": vendor_list,
                "total": len(vendor_list)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search vendors: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
