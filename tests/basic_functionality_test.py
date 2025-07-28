#!/usr/bin/env python3
"""
Basic Functionality Test for Flow-Backend
Tests core database operations and service health without complex authentication
"""

import asyncio
import aiohttp
import asyncpg
import json
import logging
import sys
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('basic_functionality_test.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Test result data structure"""
    test_name: str
    status: str  # PASS, FAIL, SKIP
    duration: float
    details: str
    error: Optional[str] = None

class BasicFunctionalityTestSuite:
    """Basic functionality testing without complex authentication"""
    
    def __init__(self):
        self.test_results: List[TestResult] = []
        self.db_connection_string = self._get_db_connection_string()
        
    def _get_db_connection_string(self) -> str:
        """Get database connection string"""
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        user = os.getenv('DB_USER', 'user')
        password = os.getenv('DB_PASSWORD', 'password')
        database = os.getenv('DB_NAME', 'oxygen_platform')
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    async def _record_test_result(
        self, 
        test_name: str, 
        start_time: float, 
        success: bool, 
        details: str,
        error: Optional[str] = None
    ):
        """Record test result"""
        duration = time.time() - start_time
        status = "PASS" if success else "FAIL"
        
        result = TestResult(
            test_name=test_name,
            status=status,
            duration=duration,
            details=details,
            error=error
        )
        
        self.test_results.append(result)
        
        status_emoji = "✅" if success else "❌"
        logger.info(f"{status_emoji} {test_name}: {status} ({duration:.2f}s)")
        
        if error:
            logger.error(f"   Error: {error}")
    
    async def test_database_connectivity(self):
        """Test direct database connectivity"""
        test_name = "Database Connectivity"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            conn = await asyncpg.connect(self.db_connection_string, timeout=10.0)
            
            # Test basic query
            result = await conn.fetchval("SELECT 1")
            
            # Test database version
            version = await conn.fetchval("SELECT version()")
            
            await conn.close()
            
            if result == 1 and version:
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Database connection successful. Version: {version[:50]}..."
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    "Database query returned unexpected results",
                    error=f"Expected 1, got {result}"
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Database connection failed",
                error=str(e)
            )
            return False
    
    async def test_database_schema(self):
        """Test database schema and tables"""
        test_name = "Database Schema Validation"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            conn = await asyncpg.connect(self.db_connection_string, timeout=10.0)
            
            # Check for critical tables
            critical_tables = ['users', 'orders', 'payments', 'notifications', 'locations', 'reviews']
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
            
            await conn.close()
            
            if len(existing_tables) == len(critical_tables):
                await self._record_test_result(
                    test_name, start_time, True,
                    f"All {len(critical_tables)} critical tables exist: {', '.join(existing_tables)}"
                )
                return True
            else:
                missing_tables = set(critical_tables) - set(existing_tables)
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Missing tables: {', '.join(missing_tables)}",
                    error=f"Found {len(existing_tables)}/{len(critical_tables)} tables"
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Schema validation failed",
                error=str(e)
            )
            return False
    
    async def test_service_health_endpoints(self):
        """Test service health endpoints directly"""
        test_name = "Service Health Endpoints"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            services = [
                ("API Gateway", "http://localhost:8000/health"),
                ("User Service", "http://localhost:8001/health"),
                ("Order Service", "http://localhost:8005/health"),
                ("Payment Service", "http://localhost:8008/health"),
                ("Location Service", "http://localhost:8003/health"),
                ("Notification Service", "http://localhost:8010/health"),
                ("Review Service", "http://localhost:8009/health"),
            ]
            
            healthy_services = []
            unhealthy_services = []
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for service_name, health_url in services:
                    try:
                        async with session.get(health_url) as response:
                            if response.status == 200:
                                healthy_services.append(service_name)
                                logger.info(f"   ✅ {service_name} is healthy")
                            else:
                                unhealthy_services.append(f"{service_name} (status: {response.status})")
                                logger.warning(f"   ⚠️ {service_name} returned status {response.status}")
                    except Exception as e:
                        unhealthy_services.append(f"{service_name} (error: {str(e)[:50]})")
                        logger.warning(f"   ❌ {service_name} is not accessible: {e}")
            
            if len(healthy_services) >= len(services) * 0.7:  # 70% success rate
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Service health check passed: {len(healthy_services)}/{len(services)} services healthy"
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Too many unhealthy services: {len(unhealthy_services)}/{len(services)}",
                    error=f"Unhealthy: {', '.join(unhealthy_services)}"
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Service health check failed",
                error=str(e)
            )
            return False
    
    async def test_database_operations(self):
        """Test basic database operations"""
        test_name = "Database Operations"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            conn = await asyncpg.connect(self.db_connection_string, timeout=10.0)
            
            # Test insert operation (create a test record)
            test_user_id = f"test_user_{int(time.time())}"
            test_email = f"test_{int(time.time())}@example.com"

            await conn.execute("""
                INSERT INTO users (id, email, password_hash, role, is_active, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, test_user_id, test_email, "dummy_hash", "hospital", True, datetime.utcnow())

            # Test select operation
            user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", test_user_id)

            # Test update operation
            await conn.execute("UPDATE users SET role = $1 WHERE id = $2", "vendor", test_user_id)

            # Verify update
            updated_user = await conn.fetchrow("SELECT role FROM users WHERE id = $1", test_user_id)

            # Test delete operation
            await conn.execute("DELETE FROM users WHERE id = $1", test_user_id)

            await conn.close()

            if user and user['email'] == test_email and updated_user and updated_user['role'] == 'vendor':
                await self._record_test_result(
                    test_name, start_time, True,
                    "Database CRUD operations successful"
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    "Database operations failed",
                    error="User record not found or incorrect data"
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Database operations failed",
                error=str(e)
            )
            return False
    
    async def run_all_tests(self):
        """Run all basic functionality tests"""
        logger.info("🚀 Starting Basic Functionality Tests")
        
        tests = [
            self.test_database_connectivity,
            self.test_database_schema,
            self.test_database_operations,
            self.test_service_health_endpoints,
        ]
        
        for test_func in tests:
            await test_func()
        
        return True
    
    def generate_test_report(self) -> str:
        """Generate test report"""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r.status == "PASS"])
        failed_tests = len([r for r in self.test_results if r.status == "FAIL"])
        
        report = f"""
# Basic Functionality Test Report
Generated: {datetime.now().isoformat()}

## Summary
- **Total Tests**: {total_tests}
- **Passed**: {passed_tests} ✅
- **Failed**: {failed_tests} ❌
- **Success Rate**: {(passed_tests/total_tests*100):.1f}%

## Test Results
"""
        
        for result in self.test_results:
            status_emoji = "✅" if result.status == "PASS" else "❌"
            report += f"\n### {status_emoji} {result.test_name}\n"
            report += f"- **Status**: {result.status}\n"
            report += f"- **Duration**: {result.duration:.2f}s\n"
            report += f"- **Details**: {result.details}\n"
            
            if result.error:
                report += f"- **Error**: {result.error}\n"
            
            report += "\n"
        
        return report

async def main():
    """Main test execution"""
    test_suite = BasicFunctionalityTestSuite()
    
    try:
        await test_suite.run_all_tests()
        
        # Generate and save report
        report = test_suite.generate_test_report()
        
        with open("basic_functionality_test_report.md", "w") as f:
            f.write(report)
        
        logger.info("📊 Test report saved to basic_functionality_test_report.md")
        
        # Print summary
        total_tests = len(test_suite.test_results)
        passed_tests = len([r for r in test_suite.test_results if r.status == "PASS"])
        
        if passed_tests == total_tests:
            logger.info(f"🎉 All {total_tests} basic functionality tests passed!")
            return 0
        else:
            logger.error(f"❌ {total_tests - passed_tests} out of {total_tests} tests failed")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Test suite failed with exception: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
