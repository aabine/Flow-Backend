from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.security import create_access_token, verify_token, get_password_hash, verify_password
from app.core.database import get_db
from app.models.user import User, UserProfile
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, UserUpdate
from app.services.user_service import UserService
from shared.models import UserRole, APIResponse

app = FastAPI(
    title="User Service",
    description="User management and authentication service",
    version="1.0.0"
)

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
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    try:
        # Check if user already exists
        existing_user = await user_service.get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Create new user
        user = await user_service.create_user(db, user_data)
        
        return APIResponse(
            success=True,
            message="User registered successfully",
            data={
                "user_id": user.id,
                "email": user.email,
                "role": user.role
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@app.post("/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """User login."""
    try:
        # Authenticate user
        user = await user_service.authenticate_user(db, login_data.email, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )
        
        # Create access token
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id), "role": user.role}
        )
        
        # Update last login
        await user_service.update_last_login(db, user.id)
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
