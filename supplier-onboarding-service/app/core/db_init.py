"""
Supplier Onboarding Service Database Initialization
Handles database schema creation and initial data seeding for the supplier onboarding service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.supplier import Supplier
from app.models.document import Document
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for supplier onboarding service tables
SUPPLIER_ONBOARDING_SERVICE_INDEXES = [
    # Supplier indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_suppliers_business_name ON suppliers(business_name)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_registration_number ON suppliers(registration_number)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_tax_id ON suppliers(tax_identification_number)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_contact_person ON suppliers(contact_person)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_contact_phone ON suppliers(contact_phone)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_status ON suppliers(status)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_created_at ON suppliers(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_suppliers_updated_at ON suppliers(updated_at)",
    
    # Document indexes
    "CREATE INDEX IF NOT EXISTS idx_documents_supplier_id ON documents(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_file_name ON documents(file_name)",
    "CREATE INDEX IF NOT EXISTS idx_documents_file_type ON documents(file_type)",
    "CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at)",
]

# Define constraints for supplier onboarding service tables (format: table_name:constraint_name:constraint_definition)
SUPPLIER_ONBOARDING_SERVICE_CONSTRAINTS = [
    # Supplier constraints
    "suppliers:chk_supplier_status:CHECK (status IN ('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED', 'SUSPENDED'))",
    "suppliers:chk_supplier_business_name:CHECK (length(business_name) >= 2)",
    "suppliers:chk_supplier_phone:CHECK (contact_phone IS NULL OR length(contact_phone) >= 10)",
    
    # Document constraints
    "documents:chk_document_file_name:CHECK (length(file_name) > 0)",
    "documents:chk_document_file_type:CHECK (file_type IN ('pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'))",
    "documents:chk_document_file_url:CHECK (length(file_url) > 0)",
]

# Define PostgreSQL extensions needed
SUPPLIER_ONBOARDING_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
SUPPLIER_ONBOARDING_SERVICE_ENUM_DATA = {
    # No enum tables for supplier onboarding service currently
}

async def create_supplier_enum_types(engine):
    """Create enum types for supplier onboarding service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create supplier status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE supplier_status_enum AS ENUM ('PENDING_VERIFICATION', 'VERIFIED', 'REJECTED', 'SUSPENDED');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create document type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE document_type_enum AS ENUM ('pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created supplier onboarding service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_supplier_functions(engine):
    """Create PostgreSQL functions for supplier onboarding operations"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to update supplier status
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_supplier_status(
                    p_supplier_id UUID,
                    p_new_status supplier_status_enum,
                    p_rejection_reason TEXT DEFAULT NULL
                )
                RETURNS BOOLEAN AS $$
                DECLARE
                    updated_rows INTEGER;
                BEGIN
                    UPDATE suppliers 
                    SET status = p_new_status,
                        rejection_reason = CASE 
                            WHEN p_new_status = 'REJECTED' THEN p_rejection_reason
                            ELSE NULL
                        END,
                        updated_at = NOW()
                    WHERE id = p_supplier_id;
                    
                    GET DIAGNOSTICS updated_rows = ROW_COUNT;
                    RETURN updated_rows > 0;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to get supplier statistics
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION get_supplier_statistics()
                RETURNS TABLE(
                    total_suppliers BIGINT,
                    pending_verification BIGINT,
                    verified_suppliers BIGINT,
                    rejected_suppliers BIGINT,
                    suspended_suppliers BIGINT
                ) AS $$
                BEGIN
                    RETURN QUERY
                    SELECT 
                        COUNT(*) as total_suppliers,
                        COUNT(*) FILTER (WHERE status = 'PENDING_VERIFICATION') as pending_verification,
                        COUNT(*) FILTER (WHERE status = 'VERIFIED') as verified_suppliers,
                        COUNT(*) FILTER (WHERE status = 'REJECTED') as rejected_suppliers,
                        COUNT(*) FILTER (WHERE status = 'SUSPENDED') as suspended_suppliers
                    FROM suppliers;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to clean up old rejected applications
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION cleanup_old_rejected_suppliers(days_old INTEGER DEFAULT 365)
                RETURNS INTEGER AS $$
                DECLARE
                    deleted_count INTEGER;
                BEGIN
                    -- Delete old rejected suppliers and their documents
                    WITH deleted_suppliers AS (
                        DELETE FROM suppliers 
                        WHERE status = 'REJECTED' 
                        AND created_at < NOW() - INTERVAL '1 day' * days_old
                        RETURNING id
                    )
                    DELETE FROM documents 
                    WHERE supplier_id IN (SELECT id FROM deleted_suppliers);
                    
                    GET DIAGNOSTICS deleted_count = ROW_COUNT;
                    RETURN deleted_count;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            logger.info("✅ Created supplier onboarding service functions")
            
    except Exception as e:
        logger.error(f"❌ Failed to create functions: {e}")
        raise

async def create_supplier_triggers(engine):
    """Create triggers for supplier onboarding operations"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to log status changes
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION log_supplier_status_change()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Log status changes (could be extended to write to audit table)
                    IF OLD.status IS DISTINCT FROM NEW.status THEN
                        -- For now, just ensure updated_at is set
                        NEW.updated_at = NOW();
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for status changes
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_log_supplier_status_change ON suppliers;
                CREATE TRIGGER trigger_log_supplier_status_change
                    BEFORE UPDATE ON suppliers
                    FOR EACH ROW
                    EXECUTE FUNCTION log_supplier_status_change();
            """))
            
            logger.info("✅ Created supplier onboarding service triggers")
            
    except Exception as e:
        logger.error(f"❌ Failed to create triggers: {e}")
        raise

async def seed_sample_supplier_data(engine):
    """Seed sample supplier data for testing"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    try:
        async with AsyncSession(engine) as session:
            # Check if sample data already exists
            result = await session.execute(select(Supplier).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Sample supplier data already exists")
                return
            
            # This would be where you add sample data
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for supplier data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed sample supplier data: {e}")
        raise

# Create the initialization function for supplier onboarding service
initialize_supplier_onboarding_database = create_service_init_function(
    service_name="supplier_onboarding",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=SUPPLIER_ONBOARDING_SERVICE_INDEXES,
    constraints=SUPPLIER_ONBOARDING_SERVICE_CONSTRAINTS,
    extensions=SUPPLIER_ONBOARDING_SERVICE_EXTENSIONS,
    enum_data=SUPPLIER_ONBOARDING_SERVICE_ENUM_DATA,
    custom_functions=[create_supplier_enum_types, create_supplier_functions, create_supplier_triggers, seed_sample_supplier_data]
)

async def init_supplier_onboarding_database() -> bool:
    """
    Initialize the supplier onboarding service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing supplier onboarding service database...")
        success = await initialize_supplier_onboarding_database()
        
        if success:
            logger.info("✅ Supplier onboarding service database initialization completed successfully")
        else:
            logger.error("❌ Supplier onboarding service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Supplier onboarding service database initialization error: {e}")
        return False
