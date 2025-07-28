"""
Delivery Service Database Initialization
Handles database schema creation and initial data seeding for the delivery service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.delivery import Driver, Delivery, DeliveryTracking, DeliveryRoute
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for delivery service tables
DELIVERY_SERVICE_INDEXES = [
    # Driver indexes
    "CREATE INDEX IF NOT EXISTS idx_drivers_user_id ON drivers(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_license ON drivers(driver_license)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_status ON drivers(status)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_vehicle_type ON drivers(vehicle_type)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_location ON drivers(current_location_lat, current_location_lng)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_rating ON drivers(rating)",
    "CREATE INDEX IF NOT EXISTS idx_drivers_active ON drivers(is_active)",
    
    # Delivery indexes
    "CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_customer_id ON deliveries(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_driver_id ON deliveries(driver_id)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_priority ON deliveries(priority)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_cylinder_size ON deliveries(cylinder_size)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_pickup_location ON deliveries(pickup_lat, pickup_lng)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_delivery_location ON deliveries(delivery_lat, delivery_lng)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_requested_time ON deliveries(requested_delivery_time)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_estimated_delivery ON deliveries(estimated_delivery_time)",
    "CREATE INDEX IF NOT EXISTS idx_deliveries_created_at ON deliveries(created_at)",
    
    # Delivery tracking indexes
    "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_delivery_id ON delivery_tracking(delivery_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_status ON delivery_tracking(status)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_timestamp ON delivery_tracking(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_created_by ON delivery_tracking(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_location ON delivery_tracking(location_lat, location_lng)",
    
    # Delivery route indexes
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_driver_id ON delivery_routes(driver_id)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_status ON delivery_routes(status)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_started_at ON delivery_routes(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_completed_at ON delivery_routes(completed_at)",
    "CREATE INDEX IF NOT EXISTS idx_delivery_routes_distance ON delivery_routes(total_distance_km)",
]

# Define constraints for delivery service tables (format: table_name:constraint_name:constraint_definition)
DELIVERY_SERVICE_CONSTRAINTS = [
    # Driver constraints
    "drivers:chk_driver_status:CHECK (status IN ('AVAILABLE', 'BUSY', 'OFF_DUTY', 'UNAVAILABLE'))",
    "drivers:chk_vehicle_type:CHECK (vehicle_type IN ('MOTORCYCLE', 'CAR', 'VAN', 'TRUCK'))",
    "drivers:chk_vehicle_capacity:CHECK (vehicle_capacity > 0)",
    "drivers:chk_rating:CHECK (rating >= 0 AND rating <= 5)",
    "drivers:chk_total_deliveries:CHECK (total_deliveries >= 0)",
    "drivers:chk_location_coords:CHECK ((current_location_lat IS NULL AND current_location_lng IS NULL) OR (current_location_lat BETWEEN -90 AND 90 AND current_location_lng BETWEEN -180 AND 180))",
    
    # Delivery constraints
    "deliveries:chk_delivery_status:CHECK (status IN ('PENDING', 'ASSIGNED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED'))",
    "deliveries:chk_delivery_priority:CHECK (priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT'))",
    "deliveries:chk_quantity:CHECK (quantity > 0)",
    "deliveries:chk_pickup_coords:CHECK (pickup_lat BETWEEN -90 AND 90 AND pickup_lng BETWEEN -180 AND 180)",
    "deliveries:chk_delivery_coords:CHECK (delivery_lat BETWEEN -90 AND 90 AND delivery_lng BETWEEN -180 AND 180)",
    "deliveries:chk_distance:CHECK (distance_km IS NULL OR distance_km >= 0)",
    "deliveries:chk_delivery_fee:CHECK (delivery_fee >= 0)",
    
    # Delivery tracking constraints
    "delivery_tracking:chk_tracking_status:CHECK (status IN ('PENDING', 'ASSIGNED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED'))",
    "delivery_tracking:chk_tracking_coords:CHECK ((location_lat IS NULL AND location_lng IS NULL) OR (location_lat BETWEEN -90 AND 90 AND location_lng BETWEEN -180 AND 180))",
    
    # Delivery route constraints
    "delivery_routes:chk_route_status:CHECK (status IN ('PLANNED', 'ACTIVE', 'COMPLETED'))",
    "delivery_routes:chk_route_distance:CHECK (total_distance_km >= 0)",
    "delivery_routes:chk_route_duration:CHECK (estimated_duration_minutes > 0)",
]

# Define PostgreSQL extensions needed
DELIVERY_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
    "postgis",    # For geospatial operations (optional, will warn if not available)
]

# Define enum data to seed
DELIVERY_SERVICE_ENUM_DATA = {
    # No enum tables for delivery service currently
}

async def create_delivery_enum_types(engine):
    """Create enum types for delivery service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create delivery status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE delivery_status_enum AS ENUM ('PENDING', 'ASSIGNED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create delivery priority enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE delivery_priority_enum AS ENUM ('LOW', 'NORMAL', 'HIGH', 'URGENT');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create driver status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE driver_status_enum AS ENUM ('AVAILABLE', 'BUSY', 'OFF_DUTY', 'UNAVAILABLE');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create vehicle type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE vehicle_type_enum AS ENUM ('MOTORCYCLE', 'CAR', 'VAN', 'TRUCK');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created delivery service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_delivery_triggers(engine):
    """Create triggers for delivery tracking and statistics"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to update driver statistics
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_driver_stats()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Update total deliveries count when delivery is completed
                    IF NEW.status = 'DELIVERED' AND (OLD.status IS NULL OR OLD.status != 'DELIVERED') THEN
                        UPDATE drivers 
                        SET total_deliveries = total_deliveries + 1
                        WHERE id = NEW.driver_id;
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for delivery completion
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_update_driver_stats ON deliveries;
                CREATE TRIGGER trigger_update_driver_stats
                    AFTER UPDATE ON deliveries
                    FOR EACH ROW
                    EXECUTE FUNCTION update_driver_stats();
            """))
            
            # Function to auto-create tracking entry
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION auto_create_tracking()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Create initial tracking entry when delivery status changes
                    INSERT INTO delivery_tracking (delivery_id, status, created_by, notes)
                    VALUES (NEW.id, NEW.status, COALESCE(NEW.driver_id, '00000000-0000-0000-0000-000000000000'::uuid), 'Status updated automatically');
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for automatic tracking
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_auto_create_tracking ON deliveries;
                CREATE TRIGGER trigger_auto_create_tracking
                    AFTER UPDATE OF status ON deliveries
                    FOR EACH ROW
                    WHEN (OLD.status IS DISTINCT FROM NEW.status)
                    EXECUTE FUNCTION auto_create_tracking();
            """))
            
            logger.info("✅ Created delivery service triggers")
            
    except Exception as e:
        logger.error(f"❌ Failed to create triggers: {e}")
        raise

async def create_geospatial_functions(engine):
    """Create geospatial functions if PostGIS is available"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Check if PostGIS is available
            result = await conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')"
            ))
            postgis_available = result.scalar()
            
            if postgis_available:
                # Function to calculate distance between two points
                await conn.execute(text("""
                    CREATE OR REPLACE FUNCTION calculate_delivery_distance(
                        pickup_lat FLOAT,
                        pickup_lng FLOAT,
                        delivery_lat FLOAT,
                        delivery_lng FLOAT
                    )
                    RETURNS FLOAT AS $$
                    BEGIN
                        RETURN ST_Distance(
                            ST_GeogFromText('POINT(' || pickup_lng || ' ' || pickup_lat || ')'),
                            ST_GeogFromText('POINT(' || delivery_lng || ' ' || delivery_lat || ')')
                        ) / 1000.0; -- Convert to kilometers
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                
                logger.info("✅ Created PostGIS geospatial functions")
            else:
                logger.info("ℹ️ PostGIS not available, skipping geospatial functions")
                
    except Exception as e:
        logger.warning(f"⚠️ Failed to create geospatial functions: {e}")
        # Don't raise - this is optional

# Create the initialization function for delivery service
initialize_delivery_database = create_service_init_function(
    service_name="delivery",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=DELIVERY_SERVICE_INDEXES,
    constraints=DELIVERY_SERVICE_CONSTRAINTS,
    extensions=DELIVERY_SERVICE_EXTENSIONS,
    enum_data=DELIVERY_SERVICE_ENUM_DATA,
    custom_functions=[create_delivery_enum_types, create_delivery_triggers, create_geospatial_functions]
)

async def init_delivery_database() -> bool:
    """
    Initialize the delivery service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing delivery service database...")
        success = await initialize_delivery_database()
        
        if success:
            logger.info("✅ Delivery service database initialization completed successfully")
        else:
            logger.error("❌ Delivery service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Delivery service database initialization error: {e}")
        return False
