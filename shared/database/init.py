"""
Shared Database Initialization Framework
Provides consistent database initialization across all microservices
"""

import asyncio
import asyncpg
import logging
import os
import sys
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy import text
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database configuration for service initialization"""
    service_name: str
    database_url: str
    schema_name: Optional[str] = None
    max_retries: int = 10
    initial_delay: float = 1.0
    max_delay: float = 30.0
    timeout: float = 30.0

class DatabaseInitializer:
    """
    Database initialization framework for microservices.
    Handles schema creation, table initialization, and data seeding.
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine: Optional[AsyncEngine] = None
        self.connection = None
        self.initialization_log = []
        
    async def initialize(self, 
                        models: List[DeclarativeMeta],
                        custom_init_functions: Optional[List[Callable]] = None,
                        seed_data_functions: Optional[List[Callable]] = None) -> bool:
        """
        Complete database initialization process.
        
        Args:
            models: SQLAlchemy model classes to create tables for
            custom_init_functions: Custom initialization functions to run
            seed_data_functions: Functions to seed initial data
            
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info(f"🚀 Starting database initialization for {self.config.service_name}")
            
            # Step 1: Wait for database to be ready
            if not await self._wait_for_database():
                logger.error(f"❌ Database not ready for {self.config.service_name}")
                return False
            
            # Step 2: Create database engine and connection
            if not await self._create_engine():
                logger.error(f"❌ Failed to create engine for {self.config.service_name}")
                return False
            
            # Step 3: Create schema if specified
            if self.config.schema_name:
                if not await self._create_schema():
                    logger.error(f"❌ Failed to create schema for {self.config.service_name}")
                    return False
            
            # Step 4: Create tables from models
            if not await self._create_tables(models):
                logger.error(f"❌ Failed to create tables for {self.config.service_name}")
                return False
            
            # Step 5: Run custom initialization functions
            if custom_init_functions:
                if not await self._run_custom_functions(custom_init_functions, "initialization"):
                    logger.error(f"❌ Custom initialization failed for {self.config.service_name}")
                    return False
            
            # Step 6: Seed initial data
            if seed_data_functions:
                if not await self._run_custom_functions(seed_data_functions, "data seeding"):
                    logger.error(f"❌ Data seeding failed for {self.config.service_name}")
                    return False
            
            # Step 7: Verify initialization
            if not await self._verify_initialization():
                logger.error(f"❌ Initialization verification failed for {self.config.service_name}")
                return False
            
            logger.info(f"✅ Database initialization completed successfully for {self.config.service_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed for {self.config.service_name}: {e}")
            return False
        finally:
            await self._cleanup()
    
    async def _wait_for_database(self) -> bool:
        """Wait for database to be ready with exponential backoff"""
        logger.info(f"⏳ Waiting for database to be ready for {self.config.service_name}...")
        
        retry_delay = self.config.initial_delay
        
        for attempt in range(self.config.max_retries):
            try:
                # Extract connection details from URL
                db_url = self.config.database_url.replace("postgresql+asyncpg://", "postgresql://")
                
                # Test connection
                conn = await asyncpg.connect(db_url, timeout=5.0)
                await conn.fetchval("SELECT 1")
                await conn.close()
                
                logger.info(f"✅ Database ready for {self.config.service_name}")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ Database not ready (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, self.config.max_delay)
        
        return False
    
    async def _create_engine(self) -> bool:
        """Create SQLAlchemy async engine"""
        try:
            self.engine = create_async_engine(
                self.config.database_url,
                echo=False,  # Set to True for SQL debugging
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "server_settings": {
                        "application_name": f"flow_backend_{self.config.service_name}",
                    }
                }
            )
            
            # Test the engine
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            logger.info(f"✅ Database engine created for {self.config.service_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create database engine for {self.config.service_name}: {e}")
            return False
    
    async def _create_schema(self) -> bool:
        """Create database schema if it doesn't exist"""
        try:
            async with self.engine.begin() as conn:
                # Check if schema exists
                result = await conn.execute(text(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema_name"
                ), {"schema_name": self.config.schema_name})
                
                if not result.fetchone():
                    # Create schema
                    await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {self.config.schema_name}"))
                    logger.info(f"✅ Created schema '{self.config.schema_name}' for {self.config.service_name}")
                else:
                    logger.info(f"✅ Schema '{self.config.schema_name}' already exists for {self.config.service_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create schema for {self.config.service_name}: {e}")
            return False
    
    async def _create_tables(self, models: List[DeclarativeMeta]) -> bool:
        """Create tables from SQLAlchemy models"""
        try:
            if not models:
                logger.info(f"ℹ️ No models provided for {self.config.service_name}")
                return True

            # Get metadata from the first model
            metadata = models[0].metadata

            async with self.engine.begin() as conn:
                # Set search path if schema is specified
                if self.config.schema_name:
                    await conn.execute(text(f"SET search_path TO {self.config.schema_name}, public"))

                # Create all tables using metadata
                await conn.run_sync(metadata.create_all)

            logger.info(f"✅ Created tables for {self.config.service_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create tables for {self.config.service_name}: {e}")
            return False
    
    async def _run_custom_functions(self, functions: List[Callable], function_type: str) -> bool:
        """Run custom initialization or seeding functions"""
        try:
            for i, func in enumerate(functions):
                logger.info(f"🔧 Running {function_type} function {i+1}/{len(functions)} for {self.config.service_name}")
                
                if asyncio.iscoroutinefunction(func):
                    await func(self.engine)
                else:
                    func(self.engine)
            
            logger.info(f"✅ Completed {function_type} for {self.config.service_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed {function_type} for {self.config.service_name}: {e}")
            return False
    
    async def _verify_initialization(self) -> bool:
        """Verify that initialization was successful"""
        try:
            async with self.engine.begin() as conn:
                # Basic connectivity test
                await conn.execute(text("SELECT 1"))
                
                # Check if we can query information_schema (indicates proper setup)
                await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' LIMIT 1"
                ))
            
            logger.info(f"✅ Database initialization verified for {self.config.service_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database verification failed for {self.config.service_name}: {e}")
            return False
    
    async def _cleanup(self):
        """Clean up resources"""
        if self.engine:
            await self.engine.dispose()
            logger.info(f"🧹 Cleaned up database resources for {self.config.service_name}")

def get_database_config(service_name: str, schema_name: Optional[str] = None) -> DatabaseConfig:
    """
    Get database configuration for a service from environment variables.
    
    Args:
        service_name: Name of the service
        schema_name: Optional schema name for the service
        
    Returns:
        DatabaseConfig: Configuration object
    """
    database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://user:password@postgres:5432/oxygen_platform')
    
    return DatabaseConfig(
        service_name=service_name,
        database_url=database_url,
        schema_name=schema_name,
        max_retries=int(os.getenv('DB_INIT_MAX_RETRIES', '10')),
        initial_delay=float(os.getenv('DB_INIT_INITIAL_DELAY', '1.0')),
        max_delay=float(os.getenv('DB_INIT_MAX_DELAY', '30.0')),
        timeout=float(os.getenv('DB_INIT_TIMEOUT', '30.0'))
    )
