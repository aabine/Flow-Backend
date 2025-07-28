from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import logging
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Create async engine with connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,   # Recycle connections every hour
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """Get database session dependency."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    try:
        async with engine.begin() as conn:
            # Import all models to ensure they are registered
            from app.models import vendor, product, pricing
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise


async def close_db():
    """Close database connections."""
    try:
        await engine.dispose()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing database connections: {e}")


async def check_db_health() -> bool:
    """Check database connectivity and health."""
    try:
        async with AsyncSessionLocal() as session:
            # Simple query to test connection
            result = await session.execute("SELECT 1")
            await result.fetchone()
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Database transaction decorator
from functools import wraps
from typing import Callable, Any


def db_transaction(func: Callable) -> Callable:
    """Decorator to handle database transactions."""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        async with AsyncSessionLocal() as session:
            try:
                # Add session to kwargs if not present
                if 'db' not in kwargs:
                    kwargs['db'] = session
                
                result = await func(*args, **kwargs)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                logger.error(f"Transaction failed in {func.__name__}: {e}")
                raise
            finally:
                await session.close()
    return wrapper
