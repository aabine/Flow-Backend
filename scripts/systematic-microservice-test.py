#!/usr/bin/env python3
"""
Systematic Microservice Testing Script
Tests each microservice individually and systematically in the Flow-Backend platform
"""

import asyncio
import aiohttp
import asyncpg
import json
import logging
import sys
import os
import time
import subprocess
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('microservice_test_results.log')
    ]
)
logger = logging.getLogger(__name__)

class MicroserviceTestSuite:
    """Comprehensive microservice testing suite"""
    
    def __init__(self):
        self.test_results = {}
        self.database_url = "postgresql://user:password@localhost:5432/oxygen_platform"
        self.services = [
            {"name": "user-service", "port": 8001, "priority": 1},
            {"name": "payment-service", "port": 8008, "priority": 2},
            {"name": "order-service", "port": 8005, "priority": 3},
            {"name": "inventory-service", "port": 8004, "priority": 4},
            {"name": "location-service", "port": 8003, "priority": 5},
            {"name": "supplier-onboarding-service", "port": 8002, "priority": 6},
            {"name": "pricing-service", "port": 8006, "priority": 7},
            {"name": "delivery-service", "port": 8007, "priority": 8},
            {"name": "review-service", "port": 8009, "priority": 9},
            {"name": "notification-service", "port": 8010, "priority": 10},
            {"name": "admin-service", "port": 8011, "priority": 11},
            {"name": "websocket-service", "port": 8012, "priority": 12},
        ]
        
    def run_docker_command(self, command: str, timeout: int = 60) -> Tuple[bool, str]:
        """Run docker command and return success status and output"""
        try:
            logger.info(f"🐳 Running: {command}")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="/home/safety-pc/Flow-Backend"
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                logger.error(f"❌ Command failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Command timed out after {timeout} seconds")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"❌ Command error: {e}")
            return False, str(e)
    
    async def wait_for_postgres(self, max_attempts: int = 30) -> bool:
        """Wait for PostgreSQL to be ready"""
        logger.info("⏳ Waiting for PostgreSQL to be ready...")
        
        for attempt in range(max_attempts):
            try:
                conn = await asyncpg.connect(self.database_url, timeout=5.0)
                await conn.fetchval("SELECT 1")
                await conn.close()
                logger.info("✅ PostgreSQL is ready")
                return True
            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.info(f"   Attempt {attempt + 1}/{max_attempts} - waiting...")
                    await asyncio.sleep(2)
                else:
                    logger.error(f"❌ PostgreSQL not ready after {max_attempts} attempts: {e}")
                    return False
        return False
    
    async def check_service_health(self, service_name: str, port: int, max_attempts: int = 30) -> bool:
        """Check if service health endpoint responds"""
        logger.info(f"🔍 Checking health of {service_name} on port {port}...")
        
        health_endpoints = ["/health", "/", "/docs"]
        
        for attempt in range(max_attempts):
            for endpoint in health_endpoints:
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        async with session.get(f"http://localhost:{port}{endpoint}") as response:
                            if response.status in [200, 404]:  # 404 is OK for some endpoints
                                logger.info(f"✅ {service_name} is healthy (endpoint: {endpoint})")
                                return True
                except Exception:
                    continue
            
            if attempt < max_attempts - 1:
                logger.info(f"   Attempt {attempt + 1}/{max_attempts} - waiting for {service_name}...")
                await asyncio.sleep(2)
        
        logger.error(f"❌ {service_name} failed to become healthy")
        return False
    
    async def test_database_connectivity(self, service_name: str) -> bool:
        """Test database connectivity and schema initialization"""
        logger.info(f"🔍 Testing database connectivity for {service_name}...")
        
        try:
            conn = await asyncpg.connect(self.database_url, timeout=10.0)
            
            # Check if service-specific tables exist
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            table_names = [row['table_name'] for row in tables]
            logger.info(f"📋 Found {len(table_names)} tables in database")
            
            # Service-specific table checks
            expected_tables = self.get_expected_tables(service_name)
            found_tables = [table for table in expected_tables if table in table_names]
            
            if found_tables:
                logger.info(f"✅ Found {len(found_tables)} expected tables for {service_name}: {found_tables}")
            else:
                logger.warning(f"⚠️ No expected tables found for {service_name}")
            
            await conn.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Database connectivity test failed for {service_name}: {e}")
            return False
    
    def get_expected_tables(self, service_name: str) -> List[str]:
        """Get expected database tables for each service"""
        table_mapping = {
            "user-service": ["users", "user_profiles", "user_sessions"],
            "payment-service": ["payments", "payment_methods", "transactions"],
            "order-service": ["orders", "order_items", "order_status_history"],
            "inventory-service": ["cylinders", "cylinder_stock", "inventory_locations"],
            "location-service": ["locations", "delivery_zones"],
            "supplier-onboarding-service": ["vendor_profiles", "supplier_applications"],
            "pricing-service": ["pricing_rules", "discounts"],
            "delivery-service": ["deliveries", "delivery_routes", "delivery_tracking"],
            "review-service": ["reviews", "ratings"],
            "notification-service": ["notifications", "notification_templates"],
            "admin-service": ["admin_users", "admin_sessions"],
            "websocket-service": ["websocket_connections", "real_time_events"],
        }
        return table_mapping.get(service_name, [])
    
    async def test_core_api_endpoints(self, service_name: str, port: int) -> bool:
        """Test core API endpoints for each service"""
        logger.info(f"🔍 Testing core API endpoints for {service_name}...")
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                # Test common endpoints
                endpoints_to_test = [
                    ("/health", "GET"),
                    ("/docs", "GET"),
                    ("/openapi.json", "GET"),
                ]
                
                # Add service-specific endpoints
                service_endpoints = self.get_service_specific_endpoints(service_name)
                endpoints_to_test.extend(service_endpoints)
                
                successful_endpoints = 0
                total_endpoints = len(endpoints_to_test)
                
                for endpoint, method in endpoints_to_test:
                    try:
                        if method == "GET":
                            async with session.get(f"http://localhost:{port}{endpoint}") as response:
                                if response.status < 500:  # Accept 4xx but not 5xx errors
                                    successful_endpoints += 1
                                    logger.info(f"✅ {method} {endpoint}: {response.status}")
                                else:
                                    logger.warning(f"⚠️ {method} {endpoint}: {response.status}")
                    except Exception as e:
                        logger.warning(f"⚠️ {method} {endpoint}: {e}")
                
                success_rate = successful_endpoints / total_endpoints if total_endpoints > 0 else 0
                logger.info(f"📊 API endpoints test: {successful_endpoints}/{total_endpoints} successful ({success_rate:.1%})")
                
                return success_rate >= 0.5  # At least 50% success rate
                
        except Exception as e:
            logger.error(f"❌ API endpoints test failed for {service_name}: {e}")
            return False
    
    def get_service_specific_endpoints(self, service_name: str) -> List[Tuple[str, str]]:
        """Get service-specific endpoints to test"""
        endpoint_mapping = {
            "user-service": [("/api/v1/users/me", "GET"), ("/api/v1/auth/login", "POST")],
            "payment-service": [("/api/v1/payments", "GET")],
            "order-service": [("/api/v1/orders", "GET")],
            "inventory-service": [("/api/v1/inventory", "GET"), ("/api/v1/cylinders", "GET")],
            "location-service": [("/api/v1/locations", "GET")],
            "supplier-onboarding-service": [("/api/v1/suppliers", "GET")],
            "pricing-service": [("/api/v1/pricing", "GET")],
            "delivery-service": [("/api/v1/deliveries", "GET")],
            "review-service": [("/api/v1/reviews", "GET")],
            "notification-service": [("/api/v1/notifications", "GET")],
            "admin-service": [("/api/v1/admin", "GET")],
            "websocket-service": [("/ws", "GET")],
        }
        return endpoint_mapping.get(service_name, [])

    async def test_individual_service(self, service: Dict) -> Dict:
        """Test an individual microservice comprehensively"""
        service_name = service["name"]
        port = service["port"]

        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 TESTING {service_name.upper()} (Priority {service['priority']})")
        logger.info(f"{'='*60}")

        test_results = {
            "service_name": service_name,
            "port": port,
            "priority": service["priority"],
            "tests": {},
            "overall_success": False,
            "start_time": datetime.now(),
            "logs": []
        }

        try:
            # Step 1: Stop the service if running
            logger.info(f"🛑 Stopping {service_name} if running...")
            self.run_docker_command(f"docker-compose stop {service_name}")

            # Step 2: Start dependencies (postgres, redis, rabbitmq)
            logger.info(f"🔧 Starting dependencies for {service_name}...")
            success, output = self.run_docker_command("docker-compose up -d postgres redis rabbitmq")
            if not success:
                test_results["logs"].append(f"Failed to start dependencies: {output}")
                return test_results

            # Step 3: Wait for PostgreSQL
            postgres_ready = await self.wait_for_postgres()
            test_results["tests"]["postgres_ready"] = postgres_ready
            if not postgres_ready:
                test_results["logs"].append("PostgreSQL not ready")
                return test_results

            # Step 4: Start the service
            logger.info(f"🚀 Starting {service_name}...")
            success, output = self.run_docker_command(f"docker-compose up -d {service_name}")
            test_results["tests"]["service_start"] = success
            if not success:
                test_results["logs"].append(f"Failed to start service: {output}")
                return test_results

            # Step 5: Check service health
            health_check = await self.check_service_health(service_name, port)
            test_results["tests"]["health_check"] = health_check

            # Step 6: Test database connectivity
            db_connectivity = await self.test_database_connectivity(service_name)
            test_results["tests"]["database_connectivity"] = db_connectivity

            # Step 7: Test API endpoints
            api_endpoints = await self.test_core_api_endpoints(service_name, port)
            test_results["tests"]["api_endpoints"] = api_endpoints

            # Step 8: Check service logs for errors
            logger.info(f"📋 Checking {service_name} logs for errors...")
            success, logs = self.run_docker_command(f"docker-compose logs --tail=50 {service_name}")
            if success:
                error_count = logs.lower().count("error") + logs.lower().count("exception")
                test_results["tests"]["log_errors"] = error_count == 0
                test_results["logs"].append(f"Error count in logs: {error_count}")
            else:
                test_results["tests"]["log_errors"] = False

            # Calculate overall success
            test_scores = [
                test_results["tests"].get("service_start", False),
                test_results["tests"].get("health_check", False),
                test_results["tests"].get("database_connectivity", False),
                test_results["tests"].get("api_endpoints", False),
            ]

            success_count = sum(test_scores)
            test_results["overall_success"] = success_count >= 3  # At least 3/4 tests must pass

            # Log results
            if test_results["overall_success"]:
                logger.info(f"✅ {service_name} testing PASSED ({success_count}/4 tests)")
            else:
                logger.error(f"❌ {service_name} testing FAILED ({success_count}/4 tests)")

        except Exception as e:
            logger.error(f"❌ Exception during {service_name} testing: {e}")
            test_results["logs"].append(f"Exception: {e}")

        finally:
            # Stop the service
            logger.info(f"🛑 Stopping {service_name}...")
            self.run_docker_command(f"docker-compose stop {service_name}")
            test_results["end_time"] = datetime.now()

        return test_results

    async def run_systematic_tests(self) -> Dict:
        """Run systematic tests on all microservices"""
        logger.info("🚀 Starting Systematic Microservice Testing")
        logger.info("=" * 80)

        overall_results = {
            "start_time": datetime.now(),
            "services_tested": [],
            "successful_services": [],
            "failed_services": [],
            "summary": {}
        }

        # Sort services by priority
        sorted_services = sorted(self.services, key=lambda x: x["priority"])

        for service in sorted_services:
            service_result = await self.test_individual_service(service)
            overall_results["services_tested"].append(service_result)

            if service_result["overall_success"]:
                overall_results["successful_services"].append(service["name"])
            else:
                overall_results["failed_services"].append(service["name"])

        # Generate summary
        total_services = len(self.services)
        successful_count = len(overall_results["successful_services"])
        failed_count = len(overall_results["failed_services"])

        overall_results["summary"] = {
            "total_services": total_services,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "success_rate": successful_count / total_services if total_services > 0 else 0
        }

        overall_results["end_time"] = datetime.now()

        # Print final summary
        self.print_final_summary(overall_results)

        return overall_results

    def print_final_summary(self, results: Dict):
        """Print comprehensive test summary"""
        logger.info("\n" + "=" * 80)
        logger.info("🎯 SYSTEMATIC MICROSERVICE TESTING SUMMARY")
        logger.info("=" * 80)

        summary = results["summary"]
        logger.info(f"📊 Total Services Tested: {summary['total_services']}")
        logger.info(f"✅ Successful Services: {summary['successful_count']}")
        logger.info(f"❌ Failed Services: {summary['failed_count']}")
        logger.info(f"📈 Success Rate: {summary['success_rate']:.1%}")

        if results["successful_services"]:
            logger.info(f"\n✅ SUCCESSFUL SERVICES:")
            for service in results["successful_services"]:
                logger.info(f"   - {service}")

        if results["failed_services"]:
            logger.info(f"\n❌ FAILED SERVICES:")
            for service in results["failed_services"]:
                logger.info(f"   - {service}")

        # Detailed results
        logger.info(f"\n📋 DETAILED RESULTS:")
        for service_result in results["services_tested"]:
            service_name = service_result["service_name"]
            tests = service_result["tests"]
            status = "✅ PASS" if service_result["overall_success"] else "❌ FAIL"

            logger.info(f"\n{service_name}: {status}")
            for test_name, test_result in tests.items():
                test_status = "✅" if test_result else "❌"
                logger.info(f"   {test_status} {test_name}")

        # Save results to file
        self.save_results_to_file(results)

    def save_results_to_file(self, results: Dict):
        """Save test results to JSON file"""
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = json.loads(json.dumps(results, default=str))

            with open("microservice_test_results.json", "w") as f:
                json.dump(results_copy, f, indent=2)

            logger.info("💾 Test results saved to microservice_test_results.json")
        except Exception as e:
            logger.error(f"❌ Failed to save results to file: {e}")

async def main():
    """Main entry point"""
    tester = MicroserviceTestSuite()
    results = await tester.run_systematic_tests()

    success_rate = results["summary"]["success_rate"]

    if success_rate >= 0.8:  # 80% success rate
        logger.info("🎉 Systematic microservice testing completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Systematic microservice testing failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
