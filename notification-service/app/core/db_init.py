"""
Notification Service Database Initialization
Handles database schema creation and initial data seeding for the notification service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.notification import Notification, NotificationTemplate, NotificationPreference
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for notification service tables
NOTIFICATION_SERVICE_INDEXES = [
    # Notification table indexes
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_template_id ON notifications(template_id)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications(sent_at)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_read_at ON notifications(read_at)",
    
    # Notification template indexes
    "CREATE INDEX IF NOT EXISTS idx_notification_templates_name ON notification_templates(name)",
    "CREATE INDEX IF NOT EXISTS idx_notification_templates_type ON notification_templates(notification_type)",
    "CREATE INDEX IF NOT EXISTS idx_notification_templates_channel ON notification_templates(channel)",
    "CREATE INDEX IF NOT EXISTS idx_notification_templates_active ON notification_templates(is_active)",
    
    # Notification preference indexes
    "CREATE INDEX IF NOT EXISTS idx_notification_preferences_user_id ON notification_preferences(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_notification_preferences_email_enabled ON notification_preferences(email_enabled)",
    "CREATE INDEX IF NOT EXISTS idx_notification_preferences_sms_enabled ON notification_preferences(sms_enabled)",
    "CREATE INDEX IF NOT EXISTS idx_notification_preferences_push_enabled ON notification_preferences(push_enabled)",
    "CREATE INDEX IF NOT EXISTS idx_notification_preferences_emergency_alerts ON notification_preferences(emergency_alerts)",
]

# Define constraints for notification service tables (format: table_name:constraint_name:constraint_definition)
NOTIFICATION_SERVICE_CONSTRAINTS = [
    # Notification constraints
    "notifications:chk_notification_type:CHECK (notification_type IN ('info', 'success', 'warning', 'error', 'order_update', 'payment_update', 'delivery_update', 'system', 'emergency'))",
    "notifications:chk_notification_status:CHECK (status IN ('pending', 'sent', 'delivered', 'failed', 'read'))",
    "notifications:chk_notification_channel:CHECK (channel IN ('email', 'sms', 'push', 'in_app'))",
    
    # Notification template constraints
    "notification_templates:chk_template_type:CHECK (notification_type IN ('info', 'success', 'warning', 'error', 'order_update', 'payment_update', 'delivery_update', 'system', 'emergency'))",
    "notification_templates:chk_template_channel:CHECK (channel IN ('email', 'sms', 'push', 'in_app'))",
]

# Define PostgreSQL extensions needed
NOTIFICATION_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
NOTIFICATION_SERVICE_ENUM_DATA = {
    # No enum tables for notification service currently
}

async def create_notification_enum_types(engine):
    """Create enum types for notification service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create notification type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE notification_type_enum AS ENUM ('info', 'success', 'warning', 'error', 'order_update', 'payment_update', 'delivery_update', 'system', 'emergency');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create notification status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE notification_status_enum AS ENUM ('pending', 'sent', 'delivered', 'failed', 'read');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create notification channel enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE notification_channel_enum AS ENUM ('email', 'sms', 'push', 'in_app');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created notification service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def seed_default_templates(engine):
    """Seed default notification templates"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.notification import NotificationTemplate, NotificationType, NotificationChannel
    
    try:
        async with AsyncSession(engine) as session:
            # Check if templates already exist
            result = await session.execute(select(NotificationTemplate).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Default notification templates already exist")
                return
            
            # Default templates
            default_templates = [
                {
                    "name": "order_confirmation",
                    "subject": "Order Confirmation - #{order_number}",
                    "body": "Your order #{order_number} has been confirmed and is being processed.",
                    "notification_type": NotificationType.ORDER_UPDATE,
                    "channel": NotificationChannel.EMAIL,
                    "variables": ["order_number", "customer_name", "total_amount"]
                },
                {
                    "name": "payment_success",
                    "subject": "Payment Successful",
                    "body": "Your payment of {amount} has been processed successfully.",
                    "notification_type": NotificationType.PAYMENT_UPDATE,
                    "channel": NotificationChannel.EMAIL,
                    "variables": ["amount", "payment_method", "transaction_id"]
                },
                {
                    "name": "delivery_update",
                    "subject": "Delivery Update - Order #{order_number}",
                    "body": "Your order #{order_number} is {status}.",
                    "notification_type": NotificationType.DELIVERY_UPDATE,
                    "channel": NotificationChannel.SMS,
                    "variables": ["order_number", "status", "estimated_delivery"]
                },
                {
                    "name": "emergency_alert",
                    "subject": "Emergency Alert",
                    "body": "Emergency alert: {message}",
                    "notification_type": NotificationType.EMERGENCY,
                    "channel": NotificationChannel.PUSH,
                    "variables": ["message", "severity", "location"]
                }
            ]
            
            for template_data in default_templates:
                template = NotificationTemplate(**template_data)
                session.add(template)
            
            await session.commit()
            logger.info("✅ Seeded default notification templates")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed default templates: {e}")
        raise

async def create_notification_functions(engine):
    """Create PostgreSQL functions for notification management"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to mark notification as read
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION mark_notification_read(notification_id UUID)
                RETURNS VOID AS $$
                BEGIN
                    UPDATE notifications 
                    SET is_read = TRUE, read_at = NOW(), status = 'read'
                    WHERE id = notification_id AND is_read = FALSE;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to clean up old notifications
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION cleanup_old_notifications(days_old INTEGER DEFAULT 90)
                RETURNS INTEGER AS $$
                DECLARE
                    deleted_count INTEGER;
                BEGIN
                    DELETE FROM notifications 
                    WHERE created_at < NOW() - INTERVAL '1 day' * days_old
                    AND is_read = TRUE;
                    
                    GET DIAGNOSTICS deleted_count = ROW_COUNT;
                    RETURN deleted_count;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            logger.info("✅ Created notification management functions")
            
    except Exception as e:
        logger.error(f"❌ Failed to create functions: {e}")
        raise

# Create the initialization function for notification service
initialize_notification_database = create_service_init_function(
    service_name="notification",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=NOTIFICATION_SERVICE_INDEXES,
    constraints=NOTIFICATION_SERVICE_CONSTRAINTS,
    extensions=NOTIFICATION_SERVICE_EXTENSIONS,
    enum_data=NOTIFICATION_SERVICE_ENUM_DATA,
    custom_functions=[create_notification_enum_types, seed_default_templates, create_notification_functions]
)

async def init_notification_database() -> bool:
    """
    Initialize the notification service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing notification service database...")
        success = await initialize_notification_database()
        
        if success:
            logger.info("✅ Notification service database initialization completed successfully")
        else:
            logger.error("❌ Notification service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Notification service database initialization error: {e}")
        return False
