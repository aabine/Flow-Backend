"""
User Service Database Initialization
Handles database schema creation and initial data seeding for the user service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.user import (User, UserProfile, UserSession, VendorProfile, HospitalProfile,
                            PasswordResetToken, EmailVerificationToken)
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for user service tables
USER_SERVICE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
    "CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified)",
    "CREATE INDEX IF NOT EXISTS idx_users_mfa_enabled ON users(mfa_enabled)",
    "CREATE INDEX IF NOT EXISTS idx_users_failed_login_attempts ON users(failed_login_attempts)",
    "CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login)",

    "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_access_token ON user_sessions(access_token_jti)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token ON user_sessions(refresh_token_jti)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_active ON user_sessions(is_active)",
    
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_phone ON user_profiles(phone)",
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_city ON user_profiles(city)",
    "CREATE INDEX IF NOT EXISTS idx_user_profiles_state ON user_profiles(state)",
    
    "CREATE INDEX IF NOT EXISTS idx_vendor_profiles_user_id ON vendor_profiles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_profiles_business_name ON vendor_profiles(business_name)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_profiles_verification_status ON vendor_profiles(verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_profiles_is_active ON vendor_profiles(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_vendor_profiles_service_areas ON vendor_profiles USING GIN(service_areas)",
    
    "CREATE INDEX IF NOT EXISTS idx_hospital_profiles_user_id ON hospital_profiles(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_hospital_profiles_hospital_name ON hospital_profiles(hospital_name)",
    "CREATE INDEX IF NOT EXISTS idx_hospital_profiles_license_number ON hospital_profiles(license_number)",
    "CREATE INDEX IF NOT EXISTS idx_hospital_profiles_verification_status ON hospital_profiles(verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_hospital_profiles_emergency_contact ON hospital_profiles(emergency_contact_number)",

    # Password reset token indexes
    "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token_hash ON password_reset_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires ON password_reset_tokens(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_used ON password_reset_tokens(used_at)",

    # Email verification token indexes
    "CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user_id ON email_verification_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_token_hash ON email_verification_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_expires ON email_verification_tokens(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_used ON email_verification_tokens(used_at)",
]

# Define constraints for user service tables (format: table_name:constraint_name:constraint_definition)
USER_SERVICE_CONSTRAINTS = [
    "users:chk_user_role:CHECK (role IN ('hospital', 'vendor', 'admin'))",
    "users:chk_failed_login_attempts:CHECK (failed_login_attempts >= 0)",

    "vendor_profiles:chk_vendor_verification_status:CHECK (verification_status IN ('pending', 'verified', 'rejected', 'suspended'))",
    "vendor_profiles:chk_vendor_rating:CHECK (average_rating >= 0 AND average_rating <= 5)",
    "vendor_profiles:chk_vendor_total_orders:CHECK (total_orders >= 0)",

    "hospital_profiles:chk_hospital_verification_status:CHECK (verification_status IN ('pending', 'verified', 'rejected', 'suspended'))",
    "hospital_profiles:chk_hospital_bed_capacity:CHECK (bed_capacity > 0)",
    "hospital_profiles:chk_hospital_emergency_level:CHECK (emergency_level >= 1 AND emergency_level <= 5)",

    # Token table constraints
    "password_reset_tokens:chk_password_reset_expires:CHECK (expires_at > created_at)",
    "email_verification_tokens:chk_email_verification_expires:CHECK (expires_at > created_at)",
]

# Define PostgreSQL extensions needed
USER_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
    "citext",     # For case-insensitive text
]

# Define enum data to seed
USER_SERVICE_ENUM_DATA = {
    # No enum tables for user service currently
}

async def seed_admin_user(engine):
    """Seed initial admin user if it doesn't exist"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.core.security import get_password_hash
    
    try:
        async with AsyncSession(engine) as session:
            # Check if admin user exists
            result = await session.execute(
                select(User).where(User.email == "admin@flow-backend.com")
            )
            admin_user = result.scalar_one_or_none()
            
            if not admin_user:
                # Create admin user
                admin_user = User(
                    email="admin@flow-backend.com",
                    password_hash=get_password_hash("admin123!@#"),
                    role="admin",
                    is_active=True,
                    email_verified=True
                )
                session.add(admin_user)
                await session.commit()
                logger.info("✅ Created initial admin user")
            else:
                logger.info("ℹ️ Admin user already exists")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed admin user: {e}")
        raise

async def create_user_role_enum(engine):
    """Create user role enum type if it doesn't exist"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create enum type for user roles
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE user_role_enum AS ENUM ('hospital', 'vendor', 'admin');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create enum type for verification status
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE verification_status_enum AS ENUM ('pending', 'verified', 'rejected', 'suspended');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created user service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

# Create the initialization function for user service
initialize_user_database = create_service_init_function(
    service_name="user",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=USER_SERVICE_INDEXES,
    constraints=USER_SERVICE_CONSTRAINTS,
    extensions=USER_SERVICE_EXTENSIONS,
    enum_data=USER_SERVICE_ENUM_DATA,
    custom_functions=[create_user_role_enum, seed_admin_user]
)

async def init_user_database() -> bool:
    """
    Initialize the user service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing user service database...")
        success = await initialize_user_database()
        
        if success:
            logger.info("✅ User service database initialization completed successfully")
        else:
            logger.error("❌ User service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ User service database initialization error: {e}")
        return False
