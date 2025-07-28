"""
Admin Service Database Initialization
Handles database schema creation and initial data seeding for the admin service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.admin import AdminUser, AuditLog, SystemMetrics, DashboardWidget, SystemAlert
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for admin service tables
ADMIN_SERVICE_INDEXES = [
    # Admin user indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_admin_users_admin_level ON admin_users(admin_level)",
    "CREATE INDEX IF NOT EXISTS idx_admin_users_is_active ON admin_users(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_admin_users_last_login ON admin_users(last_login)",
    "CREATE INDEX IF NOT EXISTS idx_admin_users_session_expires ON admin_users(session_expires_at)",
    
    # Audit log indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_ip_address ON audit_logs(ip_address)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs(request_id)",
    
    # System metrics indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_system_metrics_value ON system_metrics(value)",
    "CREATE INDEX IF NOT EXISTS idx_system_metrics_unit ON system_metrics(unit)",
    
    # Dashboard widget indexes
    "CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_type ON dashboard_widgets(widget_type)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_position ON dashboard_widgets(position_x, position_y)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_active ON dashboard_widgets(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_dashboard_widgets_data_source ON dashboard_widgets(data_source)",
    
    # System alert indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_system_alerts_acknowledged_by ON system_alerts(acknowledged_by)",
    "CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved_at ON system_alerts(resolved_at)",
    "CREATE INDEX IF NOT EXISTS idx_system_alerts_threshold ON system_alerts(threshold_value)",
]

# Define constraints for admin service tables (format: table_name:constraint_name:constraint_definition)
ADMIN_SERVICE_CONSTRAINTS = [
    # Admin user constraints
    "admin_users:chk_admin_level:CHECK (admin_level IN ('admin', 'super_admin', 'moderator'))",
    "admin_users:chk_login_count:CHECK (login_count >= 0)",
    
    # Audit log constraints
    "audit_logs:chk_action_type:CHECK (action_type IN ('user_created', 'user_updated', 'user_suspended', 'user_activated', 'order_cancelled', 'review_moderated', 'supplier_approved', 'supplier_rejected', 'system_config_updated', 'bulk_action_performed'))",
    
    # System metrics constraints
    "system_metrics:chk_metric_type:CHECK (metric_type IN ('order_count', 'revenue', 'user_count', 'review_count', 'response_time', 'error_rate', 'active_sessions'))",
    
    # Dashboard widget constraints
    "dashboard_widgets:chk_widget_position:CHECK (position_x >= 0 AND position_y >= 0)",
    "dashboard_widgets:chk_widget_size:CHECK (width > 0 AND height > 0)",
    "dashboard_widgets:chk_refresh_interval:CHECK (refresh_interval > 0)",
    
    # System alert constraints
    "system_alerts:chk_alert_type:CHECK (alert_type IN ('error', 'warning', 'info'))",
    "system_alerts:chk_severity:CHECK (severity IN ('low', 'medium', 'high', 'critical'))",
    "system_alerts:chk_status:CHECK (status IN ('active', 'acknowledged', 'resolved'))",
]

# Define PostgreSQL extensions needed
ADMIN_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
ADMIN_SERVICE_ENUM_DATA = {
    # No enum tables for admin service currently
}

async def create_admin_enum_types(engine):
    """Create enum types for admin service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create admin action type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE admin_action_type_enum AS ENUM ('user_created', 'user_updated', 'user_suspended', 'user_activated', 'order_cancelled', 'review_moderated', 'supplier_approved', 'supplier_rejected', 'system_config_updated', 'bulk_action_performed');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create metric type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE metric_type_enum AS ENUM ('order_count', 'revenue', 'user_count', 'review_count', 'response_time', 'error_rate', 'active_sessions');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created admin service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_admin_functions(engine):
    """Create PostgreSQL functions for admin operations"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to log admin actions
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION log_admin_action(
                    p_admin_user_id UUID,
                    p_action_type admin_action_type_enum,
                    p_resource_type VARCHAR,
                    p_resource_id VARCHAR,
                    p_description TEXT,
                    p_old_values JSONB DEFAULT NULL,
                    p_new_values JSONB DEFAULT NULL,
                    p_ip_address VARCHAR DEFAULT NULL,
                    p_user_agent TEXT DEFAULT NULL,
                    p_request_id VARCHAR DEFAULT NULL
                )
                RETURNS UUID AS $$
                DECLARE
                    log_id UUID;
                BEGIN
                    INSERT INTO audit_logs (
                        admin_user_id, action_type, resource_type, resource_id,
                        description, old_values, new_values, ip_address, user_agent, request_id
                    ) VALUES (
                        p_admin_user_id, p_action_type, p_resource_type, p_resource_id,
                        p_description, p_old_values, p_new_values, p_ip_address, p_user_agent, p_request_id
                    ) RETURNING id INTO log_id;
                    
                    RETURN log_id;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to record system metrics
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION record_metric(
                    p_metric_type metric_type_enum,
                    p_service_name VARCHAR,
                    p_value FLOAT,
                    p_unit VARCHAR DEFAULT NULL,
                    p_metadata JSONB DEFAULT NULL,
                    p_tags JSONB DEFAULT NULL
                )
                RETURNS UUID AS $$
                DECLARE
                    metric_id UUID;
                BEGIN
                    INSERT INTO system_metrics (
                        metric_type, service_name, value, unit, metric_metadata, tags
                    ) VALUES (
                        p_metric_type, p_service_name, p_value, p_unit, p_metadata, p_tags
                    ) RETURNING id INTO metric_id;
                    
                    RETURN metric_id;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to create system alert
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION create_system_alert(
                    p_alert_type VARCHAR,
                    p_severity VARCHAR,
                    p_title VARCHAR,
                    p_message TEXT,
                    p_service_name VARCHAR,
                    p_component VARCHAR DEFAULT NULL,
                    p_details JSONB DEFAULT NULL,
                    p_threshold_value FLOAT DEFAULT NULL,
                    p_current_value FLOAT DEFAULT NULL
                )
                RETURNS UUID AS $$
                DECLARE
                    alert_id UUID;
                BEGIN
                    INSERT INTO system_alerts (
                        alert_type, severity, title, message, service_name,
                        component, details, threshold_value, current_value
                    ) VALUES (
                        p_alert_type, p_severity, p_title, p_message, p_service_name,
                        p_component, p_details, p_threshold_value, p_current_value
                    ) RETURNING id INTO alert_id;
                    
                    RETURN alert_id;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to clean up old audit logs
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(days_old INTEGER DEFAULT 365)
                RETURNS INTEGER AS $$
                DECLARE
                    deleted_count INTEGER;
                BEGIN
                    DELETE FROM audit_logs 
                    WHERE created_at < NOW() - INTERVAL '1 day' * days_old;
                    
                    GET DIAGNOSTICS deleted_count = ROW_COUNT;
                    RETURN deleted_count;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            logger.info("✅ Created admin service functions")
            
    except Exception as e:
        logger.error(f"❌ Failed to create functions: {e}")
        raise

async def seed_default_admin_data(engine):
    """Seed default admin data"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    try:
        async with AsyncSession(engine) as session:
            # Check if admin data already exists
            result = await session.execute(select(AdminUser).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Default admin data already exists")
                return
            
            # This would be where you add default admin users
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for admin data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed default admin data: {e}")
        raise

# Create the initialization function for admin service
initialize_admin_database = create_service_init_function(
    service_name="admin",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=ADMIN_SERVICE_INDEXES,
    constraints=ADMIN_SERVICE_CONSTRAINTS,
    extensions=ADMIN_SERVICE_EXTENSIONS,
    enum_data=ADMIN_SERVICE_ENUM_DATA,
    custom_functions=[create_admin_enum_types, create_admin_functions, seed_default_admin_data]
)

async def init_admin_database() -> bool:
    """
    Initialize the admin service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing admin service database...")
        success = await initialize_admin_database()
        
        if success:
            logger.info("✅ Admin service database initialization completed successfully")
        else:
            logger.error("❌ Admin service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Admin service database initialization error: {e}")
        return False
