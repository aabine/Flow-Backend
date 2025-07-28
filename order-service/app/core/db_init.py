"""
Order Service Database Initialization
Handles database schema creation and initial data seeding for the order service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for order service tables
ORDER_SERVICE_INDEXES = [
    # Order table indexes
    "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_vendor_id ON orders(vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_priority ON orders(priority)",
    "CREATE INDEX IF NOT EXISTS idx_orders_emergency ON orders(is_emergency)",
    "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_orders_delivery_date ON orders(required_delivery_date)",
    "CREATE INDEX IF NOT EXISTS idx_orders_estimated_delivery ON orders(estimated_delivery_date)",
    "CREATE INDEX IF NOT EXISTS idx_orders_actual_delivery ON orders(actual_delivery_date)",
    "CREATE INDEX IF NOT EXISTS idx_orders_order_number ON orders(order_number)",
    "CREATE INDEX IF NOT EXISTS idx_orders_location ON orders(delivery_latitude, delivery_longitude)",
    
    # Order item indexes
    "CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_supplier_id ON order_items(supplier_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_cylinder_size ON order_items(cylinder_size)",
    
    # Order status history indexes
    "CREATE INDEX IF NOT EXISTS idx_order_status_history_order_id ON order_status_history(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_status_history_status ON order_status_history(status)",
    "CREATE INDEX IF NOT EXISTS idx_order_status_history_changed_at ON order_status_history(changed_at)",
    "CREATE INDEX IF NOT EXISTS idx_order_status_history_changed_by ON order_status_history(changed_by)",
    

]

# Define constraints for order service tables (format: table_name:constraint_name:constraint_definition)
ORDER_SERVICE_CONSTRAINTS = [
    # Order constraints
    "orders:chk_order_status:CHECK (status IN ('pending', 'confirmed', 'processing', 'ready_for_pickup', 'out_for_delivery', 'delivered', 'cancelled', 'refunded'))",
    "orders:chk_order_priority:CHECK (priority IN ('low', 'normal', 'high', 'urgent', 'emergency'))",
    "orders:chk_order_total_amount:CHECK (total_amount >= 0)",
    "orders:chk_order_delivery_coords:CHECK (delivery_latitude BETWEEN -90 AND 90 AND delivery_longitude BETWEEN -180 AND 180)",

    # Order item constraints
    "order_items:chk_order_item_quantity:CHECK (quantity > 0)",
    "order_items:chk_order_item_unit_price:CHECK (unit_price >= 0)",
    "order_items:chk_order_item_total_price:CHECK (total_price >= 0)",
    "order_items:chk_order_item_cylinder_size:CHECK (cylinder_size IN ('SMALL', 'MEDIUM', 'LARGE', 'EXTRA_LARGE'))",
    

]

# Define PostgreSQL extensions needed
ORDER_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
ORDER_SERVICE_ENUM_DATA = {
    # No enum tables for order service currently
}

async def create_order_enum_types(engine):
    """Create enum types for order service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create order status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE order_status_enum AS ENUM ('pending', 'confirmed', 'processing', 'ready_for_pickup', 'out_for_delivery', 'delivered', 'cancelled', 'refunded');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create order priority enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE order_priority_enum AS ENUM ('low', 'normal', 'high', 'urgent', 'emergency');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create delivery status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE delivery_status_enum AS ENUM ('pending', 'assigned', 'picked_up', 'in_transit', 'delivered', 'failed', 'cancelled');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created order service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_order_triggers(engine):
    """Create triggers for order management"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create trigger function for order status history
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION log_order_status_change()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF OLD.status IS DISTINCT FROM NEW.status THEN
                        INSERT INTO order_status_history (order_id, previous_status, new_status, changed_at, notes)
                        VALUES (NEW.id, OLD.status, NEW.status, NOW(), 'Status changed automatically');
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for order status changes
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS order_status_change_trigger ON orders;
                CREATE TRIGGER order_status_change_trigger
                    AFTER UPDATE ON orders
                    FOR EACH ROW
                    EXECUTE FUNCTION log_order_status_change();
            """))
            
            # Create function to update order totals
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_order_total()
                RETURNS TRIGGER AS $$
                BEGIN
                    UPDATE orders 
                    SET total_amount = (
                        SELECT COALESCE(SUM(total_price), 0) 
                        FROM order_items 
                        WHERE order_id = COALESCE(NEW.order_id, OLD.order_id)
                    )
                    WHERE id = COALESCE(NEW.order_id, OLD.order_id);
                    RETURN COALESCE(NEW, OLD);
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for order total updates
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS order_total_update_trigger ON order_items;
                CREATE TRIGGER order_total_update_trigger
                    AFTER INSERT OR UPDATE OR DELETE ON order_items
                    FOR EACH ROW
                    EXECUTE FUNCTION update_order_total();
            """))
            
            logger.info("✅ Created order service triggers")
            
    except Exception as e:
        logger.error(f"❌ Failed to create triggers: {e}")
        raise

async def seed_order_status_data(engine):
    """Seed initial order status reference data"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select, text
    
    try:
        async with AsyncSession(engine) as session:
            # Create order status reference table if it doesn't exist
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS order_status_reference (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    status_code VARCHAR(50) UNIQUE NOT NULL,
                    status_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            
            # Insert status reference data
            status_data = [
                ('pending', 'Pending', 'Order has been placed and is awaiting confirmation', 1),
                ('confirmed', 'Confirmed', 'Order has been confirmed by the vendor', 2),
                ('processing', 'Processing', 'Order is being prepared for delivery', 3),
                ('ready_for_pickup', 'Ready for Pickup', 'Order is ready to be picked up for delivery', 4),
                ('out_for_delivery', 'Out for Delivery', 'Order is currently being delivered', 5),
                ('delivered', 'Delivered', 'Order has been successfully delivered', 6),
                ('cancelled', 'Cancelled', 'Order has been cancelled', 7),
                ('refunded', 'Refunded', 'Order has been refunded', 8),
            ]
            
            for status_code, status_name, description, sort_order in status_data:
                await session.execute(text("""
                    INSERT INTO order_status_reference (status_code, status_name, description, sort_order)
                    VALUES (:status_code, :status_name, :description, :sort_order)
                    ON CONFLICT (status_code) DO NOTHING
                """), {
                    "status_code": status_code,
                    "status_name": status_name,
                    "description": description,
                    "sort_order": sort_order
                })
            
            await session.commit()
            logger.info("✅ Seeded order status reference data")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed order status data: {e}")
        raise

# Create the initialization function for order service
initialize_order_database = create_service_init_function(
    service_name="order",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=ORDER_SERVICE_INDEXES,
    constraints=ORDER_SERVICE_CONSTRAINTS,
    extensions=ORDER_SERVICE_EXTENSIONS,
    enum_data=ORDER_SERVICE_ENUM_DATA,
    custom_functions=[create_order_enum_types, create_order_triggers, seed_order_status_data]
)

async def init_order_database() -> bool:
    """
    Initialize the order service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing order service database...")
        success = await initialize_order_database()
        
        if success:
            logger.info("✅ Order service database initialization completed successfully")
        else:
            logger.error("❌ Order service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Order service database initialization error: {e}")
        return False
