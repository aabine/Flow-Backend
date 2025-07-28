"""
Inventory Service Database Initialization
Handles database schema creation and initial data seeding for the inventory service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.inventory import Inventory, CylinderStock, StockMovement, StockReservation
from app.models.cylinder import (
    Cylinder, CylinderMaintenance, CylinderQualityCheck, 
    CylinderLifecycleEvent, CylinderUsageLog
)

logger = logging.getLogger(__name__)

# Define indexes for inventory service tables
INVENTORY_SERVICE_INDEXES = [
    # Inventory table indexes
    "CREATE INDEX IF NOT EXISTS idx_inventory_vendor_id ON inventory_locations(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_location_coords ON inventory_locations(latitude, longitude)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_active ON inventory_locations(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_city_state ON inventory_locations(city, state)",
    
    # Cylinder stock indexes
    "CREATE INDEX IF NOT EXISTS idx_cylinder_stock_inventory ON cylinder_stock(inventory_id)",
    "CREATE INDEX IF NOT EXISTS idx_cylinder_stock_size ON cylinder_stock(cylinder_size)",
    "CREATE INDEX IF NOT EXISTS idx_cylinder_stock_availability ON cylinder_stock(available_quantity)",
    "CREATE INDEX IF NOT EXISTS idx_cylinder_stock_threshold ON cylinder_stock(minimum_threshold)",
    
    # Stock movement indexes
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_stock_id ON stock_movements(stock_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_type ON stock_movements(movement_type)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_date ON stock_movements(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_stock_movements_user ON stock_movements(user_id)",
    
    # Stock reservation indexes
    "CREATE INDEX IF NOT EXISTS idx_stock_reservations_stock_id ON stock_reservations(stock_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_reservations_order_id ON stock_reservations(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_stock_reservations_status ON stock_reservations(status)",
    "CREATE INDEX IF NOT EXISTS idx_stock_reservations_expires ON stock_reservations(expires_at)",
    
    # Cylinder indexes
    "CREATE INDEX IF NOT EXISTS idx_cylinders_vendor ON cylinders(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_location ON cylinders(current_location_id)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_size ON cylinders(cylinder_size)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_state ON cylinders(lifecycle_state)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_condition ON cylinders(condition)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_availability ON cylinders(is_available, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_hospital ON cylinders(current_hospital_id)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_order ON cylinders(current_order_id)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_maintenance ON cylinders(requires_maintenance)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_emergency ON cylinders(is_emergency_ready)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_inspection_due ON cylinders(next_inspection_due)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_pressure_test_due ON cylinders(next_pressure_test_due)",
    "CREATE INDEX IF NOT EXISTS idx_cylinders_serial ON cylinders(serial_number)",
    
    # Cylinder maintenance indexes
    "CREATE INDEX IF NOT EXISTS idx_maintenance_cylinder ON cylinder_maintenance(cylinder_id)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_vendor ON cylinder_maintenance(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_type ON cylinder_maintenance(maintenance_type)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_scheduled ON cylinder_maintenance(scheduled_date)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_completed ON cylinder_maintenance(is_completed)",
    "CREATE INDEX IF NOT EXISTS idx_maintenance_emergency ON cylinder_maintenance(is_emergency)",
    
    # Quality check indexes
    "CREATE INDEX IF NOT EXISTS idx_quality_cylinder ON cylinder_quality_checks(cylinder_id)",
    "CREATE INDEX IF NOT EXISTS idx_quality_vendor ON cylinder_quality_checks(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_quality_type ON cylinder_quality_checks(check_type)",
    "CREATE INDEX IF NOT EXISTS idx_quality_date ON cylinder_quality_checks(check_date)",
    "CREATE INDEX IF NOT EXISTS idx_quality_status ON cylinder_quality_checks(overall_status)",
    "CREATE INDEX IF NOT EXISTS idx_quality_follow_up ON cylinder_quality_checks(follow_up_required)",
    
    # Lifecycle event indexes
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_cylinder ON cylinder_lifecycle_events(cylinder_id)",
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_event_type ON cylinder_lifecycle_events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_date ON cylinder_lifecycle_events(event_date)",
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_order ON cylinder_lifecycle_events(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_hospital ON cylinder_lifecycle_events(hospital_id)",
    "CREATE INDEX IF NOT EXISTS idx_lifecycle_vendor ON cylinder_lifecycle_events(vendor_id)",
    
    # Usage log indexes
    "CREATE INDEX IF NOT EXISTS idx_usage_cylinder ON cylinder_usage_logs(cylinder_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_hospital ON cylinder_usage_logs(hospital_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_order ON cylinder_usage_logs(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_session_start ON cylinder_usage_logs(session_start)",
    "CREATE INDEX IF NOT EXISTS idx_usage_type ON cylinder_usage_logs(usage_type)",
]

# Define constraints for inventory service tables
INVENTORY_SERVICE_CONSTRAINTS = [
    # Stock constraints
    "ALTER TABLE cylinder_stock ADD CONSTRAINT IF NOT EXISTS chk_stock_quantities CHECK (total_quantity >= 0 AND available_quantity >= 0 AND reserved_quantity >= 0)",
    "ALTER TABLE cylinder_stock ADD CONSTRAINT IF NOT EXISTS chk_stock_balance CHECK (total_quantity = available_quantity + reserved_quantity)",
    "ALTER TABLE cylinder_stock ADD CONSTRAINT IF NOT EXISTS chk_minimum_threshold CHECK (minimum_threshold >= 0)",
    
    # Stock movement constraints
    "ALTER TABLE stock_movements ADD CONSTRAINT IF NOT EXISTS chk_movement_quantity CHECK (quantity > 0)",
    "ALTER TABLE stock_movements ADD CONSTRAINT IF NOT EXISTS chk_movement_type CHECK (movement_type IN ('received', 'sold', 'reserved', 'released', 'transferred', 'adjusted', 'damaged', 'returned'))",
    
    # Stock reservation constraints
    "ALTER TABLE stock_reservations ADD CONSTRAINT IF NOT EXISTS chk_reservation_quantity CHECK (quantity > 0)",
    "ALTER TABLE stock_reservations ADD CONSTRAINT IF NOT EXISTS chk_reservation_status CHECK (status IN ('active', 'fulfilled', 'expired', 'cancelled'))",
    
    # Cylinder constraints
    "ALTER TABLE cylinders ADD CONSTRAINT IF NOT EXISTS chk_cylinder_pressure CHECK (current_pressure_bar >= 0 AND current_pressure_bar <= working_pressure_bar)",
    "ALTER TABLE cylinders ADD CONSTRAINT IF NOT EXISTS chk_cylinder_fill_level CHECK (fill_level_percentage >= 0 AND fill_level_percentage <= 100)",
    "ALTER TABLE cylinders ADD CONSTRAINT IF NOT EXISTS chk_cylinder_purity CHECK (purity_percentage >= 0 AND purity_percentage <= 100)",
    "ALTER TABLE cylinders ADD CONSTRAINT IF NOT EXISTS chk_cylinder_lifecycle_state CHECK (lifecycle_state IN ('new', 'in_service', 'maintenance', 'testing', 'retired', 'disposed'))",
    "ALTER TABLE cylinders ADD CONSTRAINT IF NOT EXISTS chk_cylinder_condition CHECK (condition IN ('excellent', 'good', 'fair', 'poor', 'damaged'))",
    
    # Maintenance constraints
    "ALTER TABLE cylinder_maintenance ADD CONSTRAINT IF NOT EXISTS chk_maintenance_type CHECK (maintenance_type IN ('routine_inspection', 'pressure_test', 'valve_service', 'repair', 'certification', 'emergency_repair'))",
    "ALTER TABLE cylinder_maintenance ADD CONSTRAINT IF NOT EXISTS chk_maintenance_cost CHECK (cost_amount >= 0)",
    "ALTER TABLE cylinder_maintenance ADD CONSTRAINT IF NOT EXISTS chk_maintenance_hours CHECK (labor_hours >= 0)",
    
    # Quality check constraints
    "ALTER TABLE cylinder_quality_checks ADD CONSTRAINT IF NOT EXISTS chk_quality_status CHECK (overall_status IN ('passed', 'failed', 'conditional', 'pending'))",
    "ALTER TABLE cylinder_quality_checks ADD CONSTRAINT IF NOT EXISTS chk_compliance_status CHECK (compliance_status IN ('compliant', 'non_compliant', 'pending_review'))",
]

# Define PostgreSQL extensions needed
INVENTORY_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
    "postgis",    # For geospatial operations (if needed for location-based queries)
]

# Define enum data to seed
INVENTORY_SERVICE_ENUM_DATA = {
    # No enum tables for inventory service currently
}

async def create_inventory_enum_types(engine):
    """Create enum types for inventory service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create cylinder size enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE cylinder_size_enum AS ENUM ('SMALL', 'MEDIUM', 'LARGE', 'EXTRA_LARGE');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create lifecycle state enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE cylinder_lifecycle_state_enum AS ENUM ('new', 'in_service', 'maintenance', 'testing', 'retired', 'disposed');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create condition enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE cylinder_condition_enum AS ENUM ('excellent', 'good', 'fair', 'poor', 'damaged');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create maintenance type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE maintenance_type_enum AS ENUM ('routine_inspection', 'pressure_test', 'valve_service', 'repair', 'certification', 'emergency_repair');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create quality check status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE quality_check_status_enum AS ENUM ('passed', 'failed', 'conditional', 'pending');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create stock movement type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE stock_movement_type_enum AS ENUM ('received', 'sold', 'reserved', 'released', 'transferred', 'adjusted', 'damaged', 'returned');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created inventory service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def seed_sample_inventory_data(engine):
    """Seed sample inventory data for testing"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from shared.models import CylinderSize
    
    try:
        async with AsyncSession(engine) as session:
            # Check if sample data already exists
            result = await session.execute(select(Inventory).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Sample inventory data already exists")
                return
            
            # This would be where you add sample data
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for inventory data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed sample inventory data: {e}")
        raise

# Create the initialization function for inventory service
initialize_inventory_database = create_service_init_function(
    service_name="inventory",
    models=[Inventory, CylinderStock, StockMovement, StockReservation, 
            Cylinder, CylinderMaintenance, CylinderQualityCheck, 
            CylinderLifecycleEvent, CylinderUsageLog],
    indexes=INVENTORY_SERVICE_INDEXES,
    constraints=INVENTORY_SERVICE_CONSTRAINTS,
    extensions=INVENTORY_SERVICE_EXTENSIONS,
    enum_data=INVENTORY_SERVICE_ENUM_DATA,
    custom_functions=[create_inventory_enum_types, seed_sample_inventory_data]
)

async def init_inventory_database() -> bool:
    """
    Initialize the inventory service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing inventory service database...")
        success = await initialize_inventory_database()
        
        if success:
            logger.info("✅ Inventory service database initialization completed successfully")
        else:
            logger.error("❌ Inventory service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Inventory service database initialization error: {e}")
        return False
