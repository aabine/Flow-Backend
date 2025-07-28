"""
Service-specific database initialization utilities
Provides helper functions for common database initialization patterns
"""

import logging
from typing import List, Optional, Callable, Dict, Any
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy import text

from .init import DatabaseInitializer, DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)

async def initialize_service_database(
    service_name: str,
    models: List[DeclarativeMeta],
    schema_name: Optional[str] = None,
    custom_init_functions: Optional[List[Callable]] = None,
    seed_data_functions: Optional[List[Callable]] = None,
    database_url: Optional[str] = None
) -> bool:
    """
    Simplified database initialization for a service.
    
    Args:
        service_name: Name of the service
        models: SQLAlchemy model classes
        schema_name: Optional schema name
        custom_init_functions: Custom initialization functions
        seed_data_functions: Data seeding functions
        database_url: Optional custom database URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get configuration
        config = get_database_config(service_name, schema_name)
        if database_url:
            config.database_url = database_url
        
        # Initialize database
        initializer = DatabaseInitializer(config)
        return await initializer.initialize(
            models=models,
            custom_init_functions=custom_init_functions,
            seed_data_functions=seed_data_functions
        )
        
    except Exception as e:
        logger.error(f"❌ Service database initialization failed for {service_name}: {e}")
        return False

async def create_indexes(engine: AsyncEngine, indexes: List[str]) -> bool:
    """
    Create database indexes.
    
    Args:
        engine: SQLAlchemy async engine
        indexes: List of CREATE INDEX statements
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            for index_sql in indexes:
                try:
                    await conn.execute(text(index_sql))
                    logger.info(f"✅ Created index: {index_sql[:50]}...")
                except Exception as e:
                    # Index might already exist, log warning but continue
                    logger.warning(f"⚠️ Index creation warning: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")
        return False

async def create_constraints(engine: AsyncEngine, constraints: List[str]) -> bool:
    """
    Create database constraints with proper PostgreSQL syntax.

    Args:
        engine: SQLAlchemy async engine
        constraints: List of constraint definitions in format "table_name:constraint_name:constraint_definition"

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            for constraint_def in constraints:
                try:
                    # Parse constraint definition
                    if ':' in constraint_def:
                        # New format: table_name:constraint_name:constraint_definition
                        parts = constraint_def.split(':', 2)
                        if len(parts) == 3:
                            table_name, constraint_name, constraint_sql = parts

                            # Check if constraint already exists
                            check_sql = """
                                SELECT COUNT(*) FROM information_schema.table_constraints
                                WHERE table_name = :table_name
                                AND constraint_name = :constraint_name
                                AND table_schema = 'public'
                            """
                            result = await conn.execute(text(check_sql), {
                                "table_name": table_name,
                                "constraint_name": constraint_name
                            })
                            exists = result.scalar() > 0

                            if not exists:
                                full_sql = f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} {constraint_sql}"
                                await conn.execute(text(full_sql))
                                logger.info(f"✅ Created constraint: {constraint_name}")
                            else:
                                logger.info(f"ℹ️ Constraint already exists: {constraint_name}")
                        else:
                            # Fallback to old format
                            await conn.execute(text(constraint_def))
                            logger.info(f"✅ Created constraint: {constraint_def[:50]}...")
                    else:
                        # Old format - try to execute directly but handle errors gracefully
                        await conn.execute(text(constraint_def))
                        logger.info(f"✅ Created constraint: {constraint_def[:50]}...")

                except Exception as e:
                    # Constraint might already exist, log warning but continue
                    logger.warning(f"⚠️ Constraint creation warning: {e}")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to create constraints: {e}")
        return False

async def seed_enum_data(engine: AsyncEngine, enum_data: Dict[str, List[str]]) -> bool:
    """
    Seed enum data into lookup tables.
    
    Args:
        engine: SQLAlchemy async engine
        enum_data: Dictionary mapping table names to enum values
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            for table_name, values in enum_data.items():
                for value in values:
                    # Use INSERT ... ON CONFLICT DO NOTHING for PostgreSQL
                    await conn.execute(text(f"""
                        INSERT INTO {table_name} (name, value) 
                        VALUES (:name, :value) 
                        ON CONFLICT (value) DO NOTHING
                    """), {"name": value.replace("_", " ").title(), "value": value})
                
                logger.info(f"✅ Seeded enum data for {table_name}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to seed enum data: {e}")
        return False

async def create_extensions(engine: AsyncEngine, extensions: List[str]) -> bool:
    """
    Create PostgreSQL extensions.

    Args:
        engine: SQLAlchemy async engine
        extensions: List of extension names

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            for extension in extensions:
                try:
                    # Quote extension names that contain hyphens or special characters
                    if '-' in extension or any(char in extension for char in [' ', '.', '+']):
                        extension_sql = f'CREATE EXTENSION IF NOT EXISTS "{extension}"'
                    else:
                        extension_sql = f"CREATE EXTENSION IF NOT EXISTS {extension}"

                    await conn.execute(text(extension_sql))
                    logger.info(f"✅ Created extension: {extension}")
                except Exception as e:
                    logger.warning(f"⚠️ Extension creation warning for {extension}: {e}")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to create extensions: {e}")
        return False

def create_service_init_function(
    service_name: str,
    models: List[DeclarativeMeta],
    indexes: Optional[List[str]] = None,
    constraints: Optional[List[str]] = None,
    extensions: Optional[List[str]] = None,
    enum_data: Optional[Dict[str, List[str]]] = None,
    custom_functions: Optional[List[Callable]] = None
) -> Callable:
    """
    Create a complete initialization function for a service.
    
    Args:
        service_name: Name of the service
        models: SQLAlchemy model classes
        indexes: List of CREATE INDEX statements
        constraints: List of constraint statements
        extensions: List of PostgreSQL extensions
        enum_data: Enum data to seed
        custom_functions: Additional custom functions
        
    Returns:
        Callable: Async function that initializes the service database
    """
    async def init_function() -> bool:
        """Initialize database for the service"""
        try:
            logger.info(f"🚀 Starting complete database initialization for {service_name}")
            
            # Prepare initialization functions
            init_functions = []
            seed_functions = []
            
            # Add extensions creation
            if extensions:
                async def create_ext(engine):
                    return await create_extensions(engine, extensions)
                init_functions.append(create_ext)
            
            # Add indexes creation
            if indexes:
                async def create_idx(engine):
                    return await create_indexes(engine, indexes)
                init_functions.append(create_idx)
            
            # Add constraints creation
            if constraints:
                async def create_const(engine):
                    return await create_constraints(engine, constraints)
                init_functions.append(create_const)
            
            # Add enum data seeding
            if enum_data:
                async def seed_enums(engine):
                    return await seed_enum_data(engine, enum_data)
                seed_functions.append(seed_enums)
            
            # Add custom functions
            if custom_functions:
                init_functions.extend(custom_functions)
            
            # Initialize the database
            success = await initialize_service_database(
                service_name=service_name,
                models=models,
                custom_init_functions=init_functions if init_functions else None,
                seed_data_functions=seed_functions if seed_functions else None
            )
            
            if success:
                logger.info(f"✅ Complete database initialization successful for {service_name}")
            else:
                logger.error(f"❌ Database initialization failed for {service_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Database initialization error for {service_name}: {e}")
            return False
    
    return init_function
