"""
WebSocket Service Database Initialization
Handles minimal database setup for the WebSocket service (stateless service)
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function

logger = logging.getLogger(__name__)

# WebSocket service is stateless and doesn't have database models
# But we still need basic database infrastructure for potential future use

# Define indexes for websocket service tables (none currently)
WEBSOCKET_SERVICE_INDEXES = [
    # No indexes needed for stateless service
]

# Define constraints for websocket service tables (none currently)
WEBSOCKET_SERVICE_CONSTRAINTS = [
    # No constraints needed for stateless service
]

# Define PostgreSQL extensions needed
WEBSOCKET_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation (basic requirement)
]

# Define enum data to seed (none currently)
WEBSOCKET_SERVICE_ENUM_DATA = {
    # No enum tables for websocket service
}

async def create_websocket_enum_types(engine):
    """Create enum types for websocket service (none currently needed)"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create connection status enum for potential future use
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE websocket_connection_status_enum AS ENUM ('connected', 'disconnected', 'reconnecting', 'error');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create event type enum for potential future use
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE websocket_event_type_enum AS ENUM ('user_message', 'system_notification', 'emergency_alert', 'order_update', 'delivery_update');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created websocket service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_websocket_functions(engine):
    """Create PostgreSQL functions for websocket service (for potential future use)"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to log websocket events (for potential future use)
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION log_websocket_event(
                    p_user_id UUID,
                    p_event_type websocket_event_type_enum,
                    p_message TEXT,
                    p_metadata JSONB DEFAULT NULL
                )
                RETURNS UUID AS $$
                DECLARE
                    event_id UUID;
                BEGIN
                    -- This function is prepared for future use
                    -- Currently, websocket service is stateless
                    event_id := gen_random_uuid();
                    
                    -- Log to application logs for now
                    RAISE NOTICE 'WebSocket Event: User %, Type %, Message %', p_user_id, p_event_type, p_message;
                    
                    RETURN event_id;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to get websocket statistics (for potential future use)
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION get_websocket_statistics()
                RETURNS TABLE(
                    service_name TEXT,
                    status TEXT,
                    message TEXT
                ) AS $$
                BEGIN
                    RETURN QUERY
                    SELECT 
                        'WebSocket Service'::TEXT as service_name,
                        'Active'::TEXT as status,
                        'Stateless real-time communication service'::TEXT as message;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            logger.info("✅ Created websocket service functions")
            
    except Exception as e:
        logger.error(f"❌ Failed to create functions: {e}")
        raise

async def verify_redis_connection():
    """Verify Redis connection for WebSocket service"""
    try:
        import redis.asyncio as redis
        from app.core.config import get_settings
        
        settings = get_settings()
        redis_client = redis.from_url(settings.redis_url)
        
        # Test Redis connection
        await redis_client.ping()
        await redis_client.close()
        
        logger.info("✅ Redis connection verified for WebSocket service")
        return True
        
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False

async def setup_websocket_infrastructure(engine):
    """Setup infrastructure for WebSocket service"""
    try:
        # Verify Redis connection
        redis_ok = await verify_redis_connection()
        if not redis_ok:
            logger.warning("⚠️ Redis connection failed - WebSocket service may not function properly")

        # Log service readiness
        logger.info("✅ WebSocket service infrastructure setup completed")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to setup WebSocket infrastructure: {e}")
        return False

# Create the initialization function for websocket service
# Note: WebSocket service is stateless, so we pass an empty models list
initialize_websocket_database = create_service_init_function(
    service_name="websocket",
    models=[],  # No models for stateless service
    indexes=WEBSOCKET_SERVICE_INDEXES,
    constraints=WEBSOCKET_SERVICE_CONSTRAINTS,
    extensions=WEBSOCKET_SERVICE_EXTENSIONS,
    enum_data=WEBSOCKET_SERVICE_ENUM_DATA,
    custom_functions=[create_websocket_enum_types, create_websocket_functions, setup_websocket_infrastructure]
)

async def init_websocket_database() -> bool:
    """
    Initialize the websocket service database.
    This is the main function called during service startup.
    
    Note: WebSocket service is stateless and doesn't require database tables,
    but we still initialize basic infrastructure for consistency.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing websocket service database...")
        success = await initialize_websocket_database()
        
        if success:
            logger.info("✅ WebSocket service database initialization completed successfully")
            logger.info("ℹ️ Note: WebSocket service is stateless - no database tables created")
        else:
            logger.error("❌ WebSocket service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ WebSocket service database initialization error: {e}")
        return False
