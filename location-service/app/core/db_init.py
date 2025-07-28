"""
Location Service Database Initialization
Handles database schema creation and initial data seeding for the location service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.location import Location, EmergencyZone, ServiceArea
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for location service tables
LOCATION_SERVICE_INDEXES = [
    # Location table indexes
    "CREATE INDEX IF NOT EXISTS idx_locations_user_id ON locations(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_locations_coordinates ON locations(latitude, longitude)",
    "CREATE INDEX IF NOT EXISTS idx_locations_city_state ON locations(city, state)",
    "CREATE INDEX IF NOT EXISTS idx_locations_type ON locations(location_type)",
    "CREATE INDEX IF NOT EXISTS idx_locations_active ON locations(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_locations_created_at ON locations(created_at)",
    
    # Emergency zone indexes
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_center_coords ON emergency_zones(center_latitude, center_longitude)",
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_severity ON emergency_zones(severity_level)",
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_active ON emergency_zones(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_created_by ON emergency_zones(created_by)",
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_activated_at ON emergency_zones(activated_at)",
    "CREATE INDEX IF NOT EXISTS idx_emergency_zones_radius ON emergency_zones(radius_km)",
    
    # Service area indexes
    "CREATE INDEX IF NOT EXISTS idx_service_areas_vendor_id ON service_areas(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_areas_center_coords ON service_areas(center_latitude, center_longitude)",
    "CREATE INDEX IF NOT EXISTS idx_service_areas_radius ON service_areas(radius_km)",
    "CREATE INDEX IF NOT EXISTS idx_service_areas_active ON service_areas(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_service_areas_delivery_fee ON service_areas(delivery_fee)",
    "CREATE INDEX IF NOT EXISTS idx_service_areas_min_order ON service_areas(minimum_order_amount)",
]

# Define constraints for location service tables (format: table_name:constraint_name:constraint_definition)
LOCATION_SERVICE_CONSTRAINTS = [
    # Location constraints
    "locations:chk_location_coordinates:CHECK (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
    "locations:chk_location_type:CHECK (location_type IN ('hospital', 'vendor', 'warehouse'))",
    
    # Emergency zone constraints
    "emergency_zones:chk_emergency_coordinates:CHECK (center_latitude BETWEEN -90 AND 90 AND center_longitude BETWEEN -180 AND 180)",
    "emergency_zones:chk_emergency_radius:CHECK (radius_km > 0)",
    "emergency_zones:chk_emergency_severity:CHECK (severity_level IN ('low', 'medium', 'high', 'critical'))",
    
    # Service area constraints
    "service_areas:chk_service_coordinates:CHECK (center_latitude BETWEEN -90 AND 90 AND center_longitude BETWEEN -180 AND 180)",
    "service_areas:chk_service_radius:CHECK (radius_km > 0)",
    "service_areas:chk_delivery_fee:CHECK (delivery_fee >= 0)",
    "service_areas:chk_minimum_order:CHECK (minimum_order_amount >= 0)",
]

# Define PostgreSQL extensions needed
LOCATION_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
    "postgis",    # For geospatial operations (optional, will warn if not available)
]

# Define enum data to seed
LOCATION_SERVICE_ENUM_DATA = {
    # No enum tables for location service currently
}

async def create_location_enum_types(engine):
    """Create enum types for location service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create location type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE location_type_enum AS ENUM ('hospital', 'vendor', 'warehouse');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create severity level enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE severity_level_enum AS ENUM ('low', 'medium', 'high', 'critical');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created location service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_geospatial_indexes(engine):
    """Create geospatial indexes if PostGIS is available"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Check if PostGIS is available
            result = await conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')"
            ))
            postgis_available = result.scalar()
            
            if postgis_available:
                # Create spatial indexes using PostGIS
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_locations_geom 
                    ON locations USING GIST (ST_Point(longitude, latitude))
                """))
                
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_emergency_zones_geom 
                    ON emergency_zones USING GIST (ST_Point(center_longitude, center_latitude))
                """))
                
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_service_areas_geom 
                    ON service_areas USING GIST (ST_Point(center_longitude, center_latitude))
                """))
                
                logger.info("✅ Created PostGIS spatial indexes")
            else:
                logger.info("ℹ️ PostGIS not available, skipping spatial indexes")
                
    except Exception as e:
        logger.warning(f"⚠️ Failed to create spatial indexes: {e}")
        # Don't raise - this is optional

async def seed_sample_locations(engine):
    """Seed sample location data for testing"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    try:
        async with AsyncSession(engine) as session:
            # Check if sample data already exists
            result = await session.execute(select(Location).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Sample location data already exists")
                return
            
            # This would be where you add sample data
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for location data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed sample location data: {e}")
        raise

# Create the initialization function for location service
initialize_location_database = create_service_init_function(
    service_name="location",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=LOCATION_SERVICE_INDEXES,
    constraints=LOCATION_SERVICE_CONSTRAINTS,
    extensions=LOCATION_SERVICE_EXTENSIONS,
    enum_data=LOCATION_SERVICE_ENUM_DATA,
    custom_functions=[create_location_enum_types, create_geospatial_indexes, seed_sample_locations]
)

async def init_location_database() -> bool:
    """
    Initialize the location service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing location service database...")
        success = await initialize_location_database()
        
        if success:
            logger.info("✅ Location service database initialization completed successfully")
        else:
            logger.error("❌ Location service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Location service database initialization error: {e}")
        return False
