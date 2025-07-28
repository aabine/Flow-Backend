"""
Payment Service Database Initialization
Handles database schema creation and initial data seeding for the payment service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function

logger = logging.getLogger(__name__)

# For now, we'll create a basic structure since payment models might not be fully defined
# This can be expanded when the payment service models are available

# Define indexes for payment service tables
PAYMENT_SERVICE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_vendor_id ON payments(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference)",
    "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
    "CREATE INDEX IF NOT EXISTS idx_payments_paystack_ref ON payments(paystack_reference)",
    "CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_payments_paid_at ON payments(paid_at)",
]

# Define constraints for payment service tables
PAYMENT_SERVICE_CONSTRAINTS = [
    "ALTER TABLE payments ADD CONSTRAINT IF NOT EXISTS chk_payment_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded'))",
    "ALTER TABLE payments ADD CONSTRAINT IF NOT EXISTS chk_payment_amount CHECK (amount >= 0)",
    "ALTER TABLE payments ADD CONSTRAINT IF NOT EXISTS chk_platform_fee CHECK (platform_fee >= 0)",
    "ALTER TABLE payments ADD CONSTRAINT IF NOT EXISTS chk_vendor_amount CHECK (vendor_amount >= 0)",
]

# Define PostgreSQL extensions needed
PAYMENT_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

async def create_payment_enum_types(engine):
    """Create enum types for payment service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create payment status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE payment_status_enum AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created payment service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_payments_table(engine):
    """Create payments table if it doesn't exist"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS payments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    order_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    vendor_id UUID,
                    reference VARCHAR(255) UNIQUE NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    platform_fee DECIMAL(10,2) DEFAULT 0.00,
                    vendor_amount DECIMAL(10,2),
                    currency VARCHAR(3) DEFAULT 'NGN',
                    status VARCHAR(50) DEFAULT 'pending',
                    payment_method VARCHAR(50),
                    provider VARCHAR(50) DEFAULT 'paystack',
                    provider_reference VARCHAR(255),
                    paystack_reference VARCHAR(255),
                    paystack_access_code VARCHAR(255),
                    authorization_url TEXT,
                    provider_response JSONB,
                    metadata JSONB,
                    paid_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ
                )
            """))
            
            logger.info("✅ Created payments table")
            
    except Exception as e:
        logger.error(f"❌ Failed to create payments table: {e}")
        raise

# Create the initialization function for payment service
initialize_payment_database = create_service_init_function(
    service_name="payment",
    models=[],  # Will be populated when payment models are available
    indexes=PAYMENT_SERVICE_INDEXES,
    constraints=PAYMENT_SERVICE_CONSTRAINTS,
    extensions=PAYMENT_SERVICE_EXTENSIONS,
    custom_functions=[create_payment_enum_types, create_payments_table]
)

async def init_payment_database() -> bool:
    """
    Initialize the payment service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing payment service database...")
        success = await initialize_payment_database()
        
        if success:
            logger.info("✅ Payment service database initialization completed successfully")
        else:
            logger.error("❌ Payment service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Payment service database initialization error: {e}")
        return False
