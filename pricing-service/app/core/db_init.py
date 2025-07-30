"""
Pricing Service Database Initialization
Handles database schema creation and initial data seeding for the pricing service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.pricing import PricingTier, PriceHistory, PriceAlert, MarketPricing
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for pricing service tables
PRICING_SERVICE_INDEXES = [
    # Pricing tier indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_unit_price ON pricing_tiers(unit_price)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_currency ON pricing_tiers(currency)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_quantity_range ON pricing_tiers(minimum_quantity, maximum_quantity)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_effective_dates ON pricing_tiers(effective_from, effective_until)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_priority ON pricing_tiers(priority_rank)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_featured ON pricing_tiers(is_featured)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_promotional ON pricing_tiers(is_promotional)",
    "CREATE INDEX IF NOT EXISTS idx_pricing_tiers_payment_terms ON pricing_tiers(payment_terms)",
    
    # Price history indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_price_history_effective_date ON price_history(effective_date)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_recorded_at ON price_history(recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_price_range ON price_history(old_unit_price, new_unit_price)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_change_percentage ON price_history(change_percentage)",
    
    # Price alert indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_target_price ON price_alerts(target_price)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_threshold ON price_alerts(price_threshold_percentage)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_notification_method ON price_alerts(notification_method)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_frequency ON price_alerts(frequency)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_last_triggered ON price_alerts(last_triggered_at)",
    "CREATE INDEX IF NOT EXISTS idx_price_alerts_expires_at ON price_alerts(expires_at)",
    
    # Market pricing indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_market_pricing_price_range ON market_pricing(minimum_price, maximum_price)",
    "CREATE INDEX IF NOT EXISTS idx_market_pricing_vendor_count ON market_pricing(vendor_count)",
    "CREATE INDEX IF NOT EXISTS idx_market_pricing_trend ON market_pricing(price_trend)",
    "CREATE INDEX IF NOT EXISTS idx_market_pricing_period ON market_pricing(period_start, period_end)",
    "CREATE INDEX IF NOT EXISTS idx_market_pricing_confidence ON market_pricing(confidence_score)",
]

# Define constraints for pricing service tables (format: table_name:constraint_name:constraint_definition)
PRICING_SERVICE_CONSTRAINTS = [
    # Pricing tier constraints
    "pricing_tiers:chk_pricing_unit_price:CHECK (unit_price >= 0)",
    "pricing_tiers:chk_pricing_currency:CHECK (currency IN ('NGN', 'USD', 'EUR', 'GBP'))",
    "pricing_tiers:chk_pricing_quantity_range:CHECK (minimum_quantity > 0 AND (maximum_quantity IS NULL OR maximum_quantity >= minimum_quantity))",
    "pricing_tiers:chk_pricing_fees:CHECK (delivery_fee >= 0 AND setup_fee >= 0 AND handling_fee >= 0 AND emergency_surcharge >= 0)",
    "pricing_tiers:chk_pricing_discounts:CHECK (bulk_discount_percentage >= 0 AND bulk_discount_percentage <= 100 AND loyalty_discount_percentage >= 0 AND loyalty_discount_percentage <= 100 AND seasonal_discount_percentage >= 0 AND seasonal_discount_percentage <= 100)",
    "pricing_tiers:chk_pricing_effective_dates:CHECK (effective_until IS NULL OR effective_until > effective_from)",
    "pricing_tiers:chk_pricing_minimum_order:CHECK (minimum_order_value IS NULL OR minimum_order_value >= 0)",
    "pricing_tiers:chk_pricing_priority:CHECK (priority_rank > 0)",
    
    # Price history constraints
    "price_history:chk_price_history_prices:CHECK (old_unit_price >= 0 AND new_unit_price >= 0)",
    "price_history:chk_price_history_fees:CHECK ((old_delivery_fee IS NULL OR old_delivery_fee >= 0) AND (new_delivery_fee IS NULL OR new_delivery_fee >= 0))",
    "price_history:chk_price_history_change_type:CHECK (change_type IN ('price_increase', 'price_decrease', 'new_tier', 'discontinued', 'fee_change', 'discount_change'))",
    "price_history:chk_price_history_percentage:CHECK (change_percentage IS NULL OR change_percentage BETWEEN -100 AND 1000)",
    
    # Price alert constraints
    "price_alerts:chk_price_alert_target:CHECK (target_price IS NULL OR target_price >= 0)",
    "price_alerts:chk_price_alert_threshold:CHECK (price_threshold_percentage IS NULL OR price_threshold_percentage BETWEEN 0 AND 100)",
    "price_alerts:chk_price_alert_type:CHECK (alert_type IN ('price_drop', 'price_increase', 'availability', 'new_vendor', 'discount_available'))",
    "price_alerts:chk_price_alert_notification:CHECK (notification_method IN ('email', 'sms', 'push', 'in_app'))",
    "price_alerts:chk_price_alert_frequency:CHECK (frequency IN ('immediate', 'daily', 'weekly', 'monthly'))",
    "price_alerts:chk_price_alert_trigger_count:CHECK (trigger_count >= 0)",
    
    # Market pricing constraints
    "market_pricing:chk_market_pricing_prices:CHECK (average_price >= 0 AND (median_price IS NULL OR median_price >= 0) AND (minimum_price IS NULL OR minimum_price >= 0) AND (maximum_price IS NULL OR maximum_price >= 0))",
    "market_pricing:chk_market_pricing_price_order:CHECK (minimum_price IS NULL OR maximum_price IS NULL OR minimum_price <= maximum_price)",
    "market_pricing:chk_market_pricing_std_dev:CHECK (price_standard_deviation IS NULL OR price_standard_deviation >= 0)",
    "market_pricing:chk_market_pricing_counts:CHECK (vendor_count >= 0 AND total_listings >= 0 AND active_listings >= 0 AND active_listings <= total_listings)",
    "market_pricing:chk_market_pricing_trend:CHECK (price_trend IN ('increasing', 'decreasing', 'stable', 'volatile'))",
    "market_pricing:chk_market_pricing_trend_percentage:CHECK (trend_percentage IS NULL OR trend_percentage BETWEEN -100 AND 100)",
    "market_pricing:chk_market_pricing_confidence:CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1)",
]

# Define PostgreSQL extensions needed
PRICING_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
PRICING_SERVICE_ENUM_DATA = {
    # No enum tables for pricing service currently
}

async def create_pricing_enum_types(engine):
    """Create enum types for pricing service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create currency enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE currency_enum AS ENUM ('NGN', 'USD', 'EUR', 'GBP');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create change type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE price_change_type_enum AS ENUM ('price_increase', 'price_decrease', 'new_tier', 'discontinued', 'fee_change', 'discount_change');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create alert type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE price_alert_type_enum AS ENUM ('price_drop', 'price_increase', 'availability', 'new_vendor', 'discount_available');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create trend enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE price_trend_enum AS ENUM ('increasing', 'decreasing', 'stable', 'volatile');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created pricing service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_pricing_functions(engine):
    """Create PostgreSQL functions for pricing operations"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to calculate effective price with discounts
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION calculate_effective_price(
                    p_unit_price DECIMAL,
                    p_quantity INTEGER,
                    p_bulk_discount DECIMAL DEFAULT 0,
                    p_loyalty_discount DECIMAL DEFAULT 0,
                    p_seasonal_discount DECIMAL DEFAULT 0
                )
                RETURNS DECIMAL AS $$
                DECLARE
                    total_discount DECIMAL;
                    effective_price DECIMAL;
                BEGIN
                    -- Calculate total discount (not cumulative, take maximum)
                    total_discount := GREATEST(p_bulk_discount, p_loyalty_discount, p_seasonal_discount);
                    
                    -- Apply discount
                    effective_price := p_unit_price * p_quantity * (1 - total_discount / 100.0);
                    
                    RETURN ROUND(effective_price, 2);
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Function to log price changes
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION log_price_change()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Log price change when unit_price is updated
                    IF OLD.unit_price != NEW.unit_price THEN
                        INSERT INTO price_history (
                            pricing_tier_id, vendor_id, product_id,
                            old_unit_price, new_unit_price,
                            change_type, change_percentage,
                            effective_date, change_reason
                        ) VALUES (
                            NEW.id, NEW.vendor_id, NEW.product_id,
                            OLD.unit_price, NEW.unit_price,
                            CASE 
                                WHEN NEW.unit_price > OLD.unit_price THEN 'price_increase'
                                ELSE 'price_decrease'
                            END,
                            ROUND(((NEW.unit_price - OLD.unit_price) / OLD.unit_price * 100), 2),
                            NEW.effective_from,
                            'Automatic price change detection'
                        );
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for price change logging (only if table exists)
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pricing_tiers') THEN
                        DROP TRIGGER IF EXISTS trigger_log_price_change ON pricing_tiers;
                        CREATE TRIGGER trigger_log_price_change
                            AFTER UPDATE ON pricing_tiers
                            FOR EACH ROW
                            EXECUTE FUNCTION log_price_change();
                    END IF;
                END $$;
            """))
            
            # Function to check price alerts
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION check_price_alerts(
                    p_product_id UUID,
                    p_vendor_id UUID,
                    p_new_price DECIMAL
                )
                RETURNS INTEGER AS $$
                DECLARE
                    alert_count INTEGER := 0;
                    alert_record RECORD;
                BEGIN
                    -- Check all active alerts for this product
                    FOR alert_record IN 
                        SELECT * FROM price_alerts 
                        WHERE product_id = p_product_id 
                        AND (vendor_id IS NULL OR vendor_id = p_vendor_id)
                        AND is_active = true
                    LOOP
                        -- Check if alert conditions are met
                        IF (alert_record.alert_type = 'price_drop' AND p_new_price <= alert_record.target_price) OR
                           (alert_record.alert_type = 'price_increase' AND p_new_price >= alert_record.target_price) THEN
                            
                            -- Update alert trigger information
                            UPDATE price_alerts 
                            SET last_triggered_at = NOW(),
                                trigger_count = trigger_count + 1,
                                last_price_checked = p_new_price
                            WHERE id = alert_record.id;
                            
                            alert_count := alert_count + 1;
                        END IF;
                    END LOOP;
                    
                    RETURN alert_count;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            logger.info("✅ Created pricing service functions")
            
    except Exception as e:
        logger.error(f"❌ Failed to create functions: {e}")
        raise

async def seed_default_pricing_data(engine):
    """Seed default pricing data"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    try:
        async with AsyncSession(engine) as session:
            # Check if pricing data already exists
            result = await session.execute(select(PricingTier).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Default pricing data already exists")
                return
            
            # This would be where you add default pricing tiers
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for pricing data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed default pricing data: {e}")
        raise

# Create the initialization function for pricing service
initialize_pricing_database = create_service_init_function(
    service_name="pricing",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=PRICING_SERVICE_INDEXES,
    constraints=PRICING_SERVICE_CONSTRAINTS,
    extensions=PRICING_SERVICE_EXTENSIONS,
    enum_data=PRICING_SERVICE_ENUM_DATA,
    custom_functions=[create_pricing_enum_types, create_pricing_functions, seed_default_pricing_data]
)

async def init_pricing_database() -> bool:
    """
    Initialize the pricing service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing pricing service database...")
        success = await initialize_pricing_database()
        
        if success:
            logger.info("✅ Pricing service database initialization completed successfully")
        else:
            logger.error("❌ Pricing service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Pricing service database initialization error: {e}")
        return False
