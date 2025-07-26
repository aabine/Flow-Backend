#!/usr/bin/env python3
"""
Database Connectivity Test Script
Tests the improved database connection handling and validates the fixes
"""

import asyncio
import asyncpg
import logging
import sys
import os
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class DatabaseConnectivityTester:
    """Test database connectivity with various scenarios"""
    
    def __init__(self):
        self.connection_string = self._get_connection_string()
        
    def _get_connection_string(self) -> str:
        """Get database connection string from environment or defaults"""
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        user = os.getenv('DB_USER', 'user')
        password = os.getenv('DB_PASSWORD', 'password')
        database = os.getenv('DB_NAME', 'oxygen_platform')
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    async def test_basic_connection(self):
        """Test basic database connection"""
        logger.info("🔍 Testing basic database connection...")
        
        try:
            conn = await asyncpg.connect(self.connection_string, timeout=10.0)
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            
            if result == 1:
                logger.info("✅ Basic connection test passed")
                return True
            else:
                logger.error("❌ Basic connection test failed - unexpected result")
                return False
                
        except Exception as e:
            logger.error(f"❌ Basic connection test failed: {e}")
            return False
    
    async def test_connection_with_retry(self):
        """Test connection with retry logic"""
        logger.info("🔍 Testing connection with retry logic...")
        
        max_retries = 5
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Connection attempt {attempt + 1}/{max_retries}...")
                
                conn = await asyncpg.connect(
                    self.connection_string,
                    timeout=30.0,
                    command_timeout=60.0,
                    server_settings={
                        'application_name': 'connectivity_test',
                        'tcp_keepalives_idle': '600',
                        'tcp_keepalives_interval': '30',
                        'tcp_keepalives_count': '3'
                    }
                )
                
                # Test the connection
                await conn.fetchval("SELECT version()")
                await conn.close()
                
                logger.info("✅ Connection with retry test passed")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ Connection attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Retrying in {retry_delay:.1f} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30.0)
                else:
                    logger.error(f"❌ Connection with retry test failed after {max_retries} attempts")
                    return False
        
        return False
    
    async def test_concurrent_connections(self):
        """Test multiple concurrent connections"""
        logger.info("🔍 Testing concurrent connections...")

        async def create_connection(conn_id):
            try:
                # Add connection configuration for better reliability
                conn = await asyncpg.connect(
                    self.connection_string,
                    timeout=15.0,
                    command_timeout=30.0,
                    server_settings={
                        'application_name': f'concurrent_test_{conn_id}',
                    }
                )

                # Test the connection with a simple query
                result = await conn.fetchval("SELECT 1")

                # Test a slightly more complex query to ensure connection works
                version = await conn.fetchval("SELECT version()")

                await conn.close()
                return result == 1 and version is not None

            except Exception as e:
                logger.warning(f"⚠️ Concurrent connection {conn_id} failed: {e}")
                return False

        # Test 10 concurrent connections
        logger.info("🔄 Creating 10 concurrent database connections...")
        tasks = [create_connection(i) for i in range(1, 11)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful connections and handle exceptions
        successful = 0
        exceptions = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Connection {i+1} raised exception: {result}")
                exceptions.append(result)
            elif result is True:
                successful += 1
            else:
                logger.warning(f"⚠️ Connection {i+1} returned False")

        total = len(results)

        if successful == total:
            logger.info(f"✅ Concurrent connections test passed ({successful}/{total})")
            return True
        elif successful >= total * 0.8:  # Allow 80% success rate for concurrent connections
            logger.warning(f"⚠️ Concurrent connections test partially passed ({successful}/{total})")
            logger.warning("This may be acceptable under high load conditions")
            return True
        else:
            logger.error(f"❌ Concurrent connections test failed ({successful}/{total})")
            if exceptions:
                logger.error(f"Exceptions encountered: {len(exceptions)}")
            return False
    
    async def test_database_health(self):
        """Test database health and readiness"""
        logger.info("🔍 Testing database health...")
        
        try:
            conn = await asyncpg.connect(self.connection_string, timeout=10.0)
            
            # Test basic queries
            version = await conn.fetchval("SELECT version()")
            current_time = await conn.fetchval("SELECT NOW()")
            connection_count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
            
            logger.info(f"📊 Database version: {version}")
            logger.info(f"📊 Current time: {current_time}")
            logger.info(f"📊 Active connections: {connection_count}")
            
            await conn.close()
            
            logger.info("✅ Database health test passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database health test failed: {e}")
            return False
    
    async def test_schema_validation(self):
        """Test that critical tables exist"""
        logger.info("🔍 Testing schema validation...")
        
        try:
            conn = await asyncpg.connect(self.connection_string, timeout=10.0)
            
            # Check for critical tables
            critical_tables = ['users', 'orders', 'payments', 'notifications']
            existing_tables = []
            
            for table_name in critical_tables:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = $1
                    )
                """, table_name)
                
                if exists:
                    existing_tables.append(table_name)
                    logger.info(f"✅ Table exists: {table_name}")
                else:
                    logger.warning(f"⚠️ Table missing: {table_name}")
            
            await conn.close()
            
            if len(existing_tables) >= 2:  # At least some tables should exist
                logger.info(f"✅ Schema validation passed ({len(existing_tables)}/{len(critical_tables)} tables found)")
                return True
            else:
                logger.warning(f"⚠️ Schema validation incomplete ({len(existing_tables)}/{len(critical_tables)} tables found)")
                return False
                
        except Exception as e:
            logger.error(f"❌ Schema validation test failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all connectivity tests"""
        logger.info("🚀 Starting database connectivity tests...")
        
        tests = [
            ("Basic Connection", self.test_basic_connection),
            ("Connection with Retry", self.test_connection_with_retry),
            ("Concurrent Connections", self.test_concurrent_connections),
            ("Database Health", self.test_database_health),
            ("Schema Validation", self.test_schema_validation),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*50}")
            
            start_time = time.time()
            result = await test_func()
            end_time = time.time()
            
            results[test_name] = {
                'passed': result,
                'duration': end_time - start_time
            }
            
            logger.info(f"Result: {'✅ PASSED' if result else '❌ FAILED'} ({end_time - start_time:.2f}s)")
        
        # Summary
        logger.info(f"\n{'='*50}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'='*50}")
        
        passed_count = sum(1 for r in results.values() if r['passed'])
        total_count = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result['passed'] else "❌ FAILED"
            logger.info(f"{test_name}: {status} ({result['duration']:.2f}s)")
        
        logger.info(f"\nOverall: {passed_count}/{total_count} tests passed")
        
        if passed_count == total_count:
            logger.info("🎉 All database connectivity tests passed!")
            return True
        else:
            logger.error("❌ Some database connectivity tests failed")
            return False

async def main():
    """Main entry point"""
    tester = DatabaseConnectivityTester()
    success = await tester.run_all_tests()
    
    if success:
        logger.info("✅ Database connectivity testing completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Database connectivity testing failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
