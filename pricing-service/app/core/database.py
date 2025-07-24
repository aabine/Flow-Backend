from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.MAX_OVERFLOW,
    poolclass=NullPool if "sqlite" in settings.DATABASE_URL else None,
    future=True
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create declarative base
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables with retry logic."""
    import asyncio
    import logging

    logger = logging.getLogger(__name__)
    max_retries = 5
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to database (attempt {attempt + 1}/{max_retries})")
            async with engine.begin() as conn:
                # Create schema if it doesn't exist
                schema_name = settings.DATABASE_SCHEMA
                await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))

                # Import all models to ensure they are registered
                from app.models import pricing

                # Set schema for all tables
                for table in Base.metadata.tables.values():
                    table.schema = schema_name

                await conn.run_sync(Base.metadata.create_all)
            logger.info(f"Database initialized successfully with schema '{schema_name}'")
            return
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("Failed to connect to database after all retries")
                raise


async def close_db():
    """Close database connections."""
    await engine.dispose()


async def check_db_health():
    """Check database connectivity."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False