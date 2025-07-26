from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from typing import Optional
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, UserProfile, HospitalProfile, VendorProfile
from app.schemas.user import UserCreate, UserUpdate, HospitalProfileCreate, VendorProfileCreate
from app.core.security import get_password_hash, verify_password
from shared.models import UserRole


class UserService:
    async def create_user(self, db: AsyncSession, user_data: UserCreate) -> User:
        """Create a new user."""
        hashed_password = get_password_hash(user_data.password)
        
        db_user = User(
            email=user_data.email,
            password_hash=hashed_password,
            role=user_data.role
        )
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        # Create user profile
        profile = UserProfile(
            user_id=db_user.id,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone_number=user_data.phone_number
        )
        
        db.add(profile)
        await db.commit()
        
        return db_user
    
    async def get_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).filter(User.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()
    
    async def authenticate_user(self, db: AsyncSession, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = await self.get_user_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user
    
    async def update_user(self, db: AsyncSession, user_id: str, user_update: UserUpdate) -> Optional[User]:
        """Update user profile."""
        # Update user profile
        stmt = update(UserProfile).where(
            UserProfile.user_id == uuid.UUID(user_id)
        ).values(**user_update.dict(exclude_unset=True))
        
        await db.execute(stmt)
        await db.commit()
        
        return await self.get_user_by_id(db, user_id)
    
    async def update_last_login(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        """Update user's last login timestamp."""
        stmt = update(User).where(User.id == user_id).values(last_login=datetime.utcnow())
        await db.execute(stmt)
        # Note: Commit is handled by the caller to maintain transaction control
    
    async def deactivate_user(self, db: AsyncSession, user_id: str) -> bool:
        """Deactivate a user."""
        stmt = update(User).where(
            User.id == uuid.UUID(user_id)
        ).values(is_active=False)
        
        result = await db.execute(stmt)
        await db.commit()
        
        return result.rowcount > 0
    
    async def create_hospital_profile(
        self, db: AsyncSession, user_id: str, profile_data: HospitalProfileCreate
    ) -> HospitalProfile:
        """Create hospital profile."""
        profile = HospitalProfile(
            user_id=uuid.UUID(user_id),
            **profile_data.dict()
        )
        
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        
        return profile
    
    async def create_vendor_profile(
        self, db: AsyncSession, user_id: str, profile_data: VendorProfileCreate
    ) -> VendorProfile:
        """Create vendor profile."""
        profile = VendorProfile(
            user_id=uuid.UUID(user_id),
            **profile_data.dict()
        )
        
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        
        return profile
    
    async def get_hospital_profile(self, db: AsyncSession, user_id: str) -> Optional[HospitalProfile]:
        """Get hospital profile by user ID."""
        result = await db.execute(
            select(HospitalProfile).filter(HospitalProfile.user_id == uuid.UUID(user_id))
        )
        return result.scalar_one_or_none()
    
    async def get_vendor_profile(self, db: AsyncSession, user_id: str) -> Optional[VendorProfile]:
        """Get vendor profile by user ID."""
        result = await db.execute(
            select(VendorProfile).filter(VendorProfile.user_id == uuid.UUID(user_id))
        )
        return result.scalar_one_or_none()
