"""
Review Service Database Initialization
Handles database schema creation and initial data seeding for the review service
"""

import logging
import sys
import os
from typing import List

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.database.service_init import create_service_init_function
from app.models.review import Review, ReviewSummary, ReviewReport, ReviewHelpfulness
from app.core.database import Base

logger = logging.getLogger(__name__)

# Define indexes for review service tables
REVIEW_SERVICE_INDEXES = [
    # Review table indexes (additional to those defined in model)
    "CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_type ON reviews(review_type)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_verified ON reviews(is_verified)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_anonymous ON reviews(is_anonymous)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_flagged_at ON reviews(flagged_at)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_helpful_count ON reviews(helpful_count)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_response_at ON reviews(response_at)",
    
    # Review summary indexes
    "CREATE INDEX IF NOT EXISTS idx_review_summaries_user_role ON review_summaries(user_role)",
    "CREATE INDEX IF NOT EXISTS idx_review_summaries_avg_rating ON review_summaries(average_rating)",
    "CREATE INDEX IF NOT EXISTS idx_review_summaries_total_reviews ON review_summaries(total_reviews)",
    "CREATE INDEX IF NOT EXISTS idx_review_summaries_last_review ON review_summaries(last_review_at)",
    "CREATE INDEX IF NOT EXISTS idx_review_summaries_verified_count ON review_summaries(verified_reviews_count)",
    
    # Review report indexes
    "CREATE INDEX IF NOT EXISTS idx_review_reports_reason ON review_reports(reason)",
    "CREATE INDEX IF NOT EXISTS idx_review_reports_status ON review_reports(status)",
    "CREATE INDEX IF NOT EXISTS idx_review_reports_reporter ON review_reports(reporter_id)",
    "CREATE INDEX IF NOT EXISTS idx_review_reports_resolved_by ON review_reports(resolved_by)",
    "CREATE INDEX IF NOT EXISTS idx_review_reports_resolved_at ON review_reports(resolved_at)",
    
    # Review helpfulness indexes
    "CREATE INDEX IF NOT EXISTS idx_review_helpfulness_is_helpful ON review_helpfulness(is_helpful)",
    "CREATE INDEX IF NOT EXISTS idx_review_helpfulness_created_at ON review_helpfulness(created_at)",
]

# Define constraints for review service tables (format: table_name:constraint_name:constraint_definition)
REVIEW_SERVICE_CONSTRAINTS = [
    # Review constraints
    "reviews:chk_review_rating:CHECK (rating >= 1 AND rating <= 5)",
    "reviews:chk_review_type:CHECK (review_type IN ('hospital_to_vendor', 'vendor_to_hospital'))",
    "reviews:chk_review_status:CHECK (status IN ('active', 'hidden', 'flagged', 'deleted'))",
    "reviews:chk_helpful_counts:CHECK (helpful_count >= 0 AND not_helpful_count >= 0)",
    
    # Review summary constraints
    "review_summaries:chk_summary_rating:CHECK (average_rating >= 0 AND average_rating <= 5)",
    "review_summaries:chk_summary_counts:CHECK (total_reviews >= 0 AND rating_1_count >= 0 AND rating_2_count >= 0 AND rating_3_count >= 0 AND rating_4_count >= 0 AND rating_5_count >= 0)",
    "review_summaries:chk_summary_verified:CHECK (verified_reviews_count >= 0 AND flagged_reviews_count >= 0)",
    
    # Review report constraints
    "review_reports:chk_report_reason:CHECK (reason IN ('spam', 'inappropriate', 'fake', 'offensive', 'irrelevant', 'other'))",
    "review_reports:chk_report_status:CHECK (status IN ('pending', 'reviewed', 'resolved', 'dismissed'))",
]

# Define PostgreSQL extensions needed
REVIEW_SERVICE_EXTENSIONS = [
    "uuid-ossp",  # For UUID generation
]

# Define enum data to seed
REVIEW_SERVICE_ENUM_DATA = {
    # No enum tables for review service currently
}

async def create_review_enum_types(engine):
    """Create enum types for review service"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Create review status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE review_status_enum AS ENUM ('active', 'hidden', 'flagged', 'deleted');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create review type enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE review_type_enum AS ENUM ('hospital_to_vendor', 'vendor_to_hospital');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create report status enum
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE report_status_enum AS ENUM ('pending', 'reviewed', 'resolved', 'dismissed');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            logger.info("✅ Created review service enum types")
            
    except Exception as e:
        logger.error(f"❌ Failed to create enum types: {e}")
        raise

async def create_review_triggers(engine):
    """Create triggers for automatic review summary updates"""
    from sqlalchemy import text
    
    try:
        async with engine.begin() as conn:
            # Function to update review summary
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_review_summary()
                RETURNS TRIGGER AS $$
                BEGIN
                    -- Update or insert review summary for the reviewee
                    INSERT INTO review_summaries (user_id, user_role, total_reviews, average_rating, 
                                                rating_1_count, rating_2_count, rating_3_count, 
                                                rating_4_count, rating_5_count, last_review_at)
                    SELECT 
                        NEW.reviewee_id,
                        'vendor'::user_role_enum,  -- Assume vendor for now, could be dynamic
                        COUNT(*),
                        AVG(rating::float),
                        COUNT(*) FILTER (WHERE rating = 1),
                        COUNT(*) FILTER (WHERE rating = 2),
                        COUNT(*) FILTER (WHERE rating = 3),
                        COUNT(*) FILTER (WHERE rating = 4),
                        COUNT(*) FILTER (WHERE rating = 5),
                        MAX(created_at)
                    FROM reviews 
                    WHERE reviewee_id = NEW.reviewee_id AND status = 'active'
                    ON CONFLICT (user_id) DO UPDATE SET
                        total_reviews = EXCLUDED.total_reviews,
                        average_rating = EXCLUDED.average_rating,
                        rating_1_count = EXCLUDED.rating_1_count,
                        rating_2_count = EXCLUDED.rating_2_count,
                        rating_3_count = EXCLUDED.rating_3_count,
                        rating_4_count = EXCLUDED.rating_4_count,
                        rating_5_count = EXCLUDED.rating_5_count,
                        last_review_at = EXCLUDED.last_review_at,
                        updated_at = NOW();
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for review inserts/updates
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_update_review_summary ON reviews;
                CREATE TRIGGER trigger_update_review_summary
                    AFTER INSERT OR UPDATE ON reviews
                    FOR EACH ROW
                    EXECUTE FUNCTION update_review_summary();
            """))
            
            # Function to update helpfulness counts
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_helpfulness_counts()
                RETURNS TRIGGER AS $$
                BEGIN
                    UPDATE reviews SET
                        helpful_count = (
                            SELECT COUNT(*) FROM review_helpfulness 
                            WHERE review_id = NEW.review_id AND is_helpful = true
                        ),
                        not_helpful_count = (
                            SELECT COUNT(*) FROM review_helpfulness 
                            WHERE review_id = NEW.review_id AND is_helpful = false
                        )
                    WHERE id = NEW.review_id;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            
            # Create trigger for helpfulness votes
            await conn.execute(text("""
                DROP TRIGGER IF EXISTS trigger_update_helpfulness_counts ON review_helpfulness;
                CREATE TRIGGER trigger_update_helpfulness_counts
                    AFTER INSERT OR UPDATE OR DELETE ON review_helpfulness
                    FOR EACH ROW
                    EXECUTE FUNCTION update_helpfulness_counts();
            """))
            
            logger.info("✅ Created review service triggers")
            
    except Exception as e:
        logger.error(f"❌ Failed to create triggers: {e}")
        raise

async def seed_sample_reviews(engine):
    """Seed sample review data for testing"""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    try:
        async with AsyncSession(engine) as session:
            # Check if sample data already exists
            result = await session.execute(select(Review).limit(1))
            if result.scalar_one_or_none():
                logger.info("ℹ️ Sample review data already exists")
                return
            
            # This would be where you add sample data
            # For now, just log that we're ready for data
            logger.info("ℹ️ Ready for review data seeding (implement as needed)")
                
    except Exception as e:
        logger.error(f"❌ Failed to seed sample review data: {e}")
        raise

# Create the initialization function for review service
initialize_review_database = create_service_init_function(
    service_name="review",
    models=[Base],  # Pass the Base class instead of model instances
    indexes=REVIEW_SERVICE_INDEXES,
    constraints=REVIEW_SERVICE_CONSTRAINTS,
    extensions=REVIEW_SERVICE_EXTENSIONS,
    enum_data=REVIEW_SERVICE_ENUM_DATA,
    custom_functions=[create_review_enum_types, create_review_triggers, seed_sample_reviews]
)

async def init_review_database() -> bool:
    """
    Initialize the review service database.
    This is the main function called during service startup.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.info("🚀 Initializing review service database...")
        success = await initialize_review_database()
        
        if success:
            logger.info("✅ Review service database initialization completed successfully")
        else:
            logger.error("❌ Review service database initialization failed")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Review service database initialization error: {e}")
        return False
