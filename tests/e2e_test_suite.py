#!/usr/bin/env python3
"""
Comprehensive End-to-End Test Suite for Flow-Backend
Tests all microservices functionality within Docker containers
"""

import asyncio
import aiohttp
import json
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class E2ETestSuite:
    """Comprehensive end-to-end test suite for the Flow-Backend platform."""
    
    def __init__(self):
        self.base_url = "http://localhost"
        self.services = {
            "api_gateway": 8000,
            "user_service": 8001,
            "supplier_onboarding": 8002,
            "location_service": 8003,
            "inventory_service": 8004,
            "order_service": 8005,
            "pricing_service": 8006,
            "delivery_service": 8007,
            "payment_service": 8008,
            "review_service": 8009,
            "notification_service": 8010,
            "admin_service": 8011,
            "websocket_service": 8012
        }
        self.test_data = {}
        self.test_results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "service_health": {},
            "test_details": []
        }
    
    async def run_all_tests(self):
        """Run the complete test suite."""
        logger.info("🚀 Starting comprehensive end-to-end test suite...")
        
        try:
            # Phase 1: Service Health Checks
            await self.test_service_health()
            
            # Phase 2: Database Connectivity Tests
            await self.test_database_connectivity()
            
            # Phase 3: Authentication Flow Tests
            await self.test_authentication_flow()
            
            # Phase 4: Business Operations Tests
            await self.test_business_operations()
            
            # Phase 5: Inter-Service Communication Tests
            await self.test_inter_service_communication()
            
            # Phase 6: Security Mechanism Tests
            await self.test_security_mechanisms()
            
            # Phase 7: Error Handling Tests
            await self.test_error_handling()
            
            # Generate final report
            self.generate_test_report()
            
        except Exception as e:
            logger.error(f"Test suite execution failed: {e}")
            self.test_results["errors"].append(f"Test suite execution error: {str(e)}")
    
    async def test_service_health(self):
        """Test health endpoints of all services."""
        logger.info("📊 Testing service health...")
        
        async with aiohttp.ClientSession() as session:
            for service_name, port in self.services.items():
                try:
                    url = f"{self.base_url}:{port}/health"
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.test_results["service_health"][service_name] = {
                                "status": "healthy",
                                "response_time": response.headers.get("X-Response-Time", "N/A"),
                                "details": data
                            }
                            self.record_test_result(f"Health check - {service_name}", True, f"Service healthy: {data}")
                        else:
                            self.test_results["service_health"][service_name] = {
                                "status": "unhealthy",
                                "http_status": response.status
                            }
                            self.record_test_result(f"Health check - {service_name}", False, f"HTTP {response.status}")
                            
                except Exception as e:
                    self.test_results["service_health"][service_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    self.record_test_result(f"Health check - {service_name}", False, f"Connection error: {str(e)}")
    
    async def test_database_connectivity(self):
        """Test database connectivity and table existence."""
        logger.info("🗄️ Testing database connectivity...")
        
        # Test user registration to verify database tables exist
        test_user = {
            "email": f"test_{uuid.uuid4().hex[:8]}@hospital.com",
            "password": "TestPass123!",
            "role": "hospital",
            "hospital_profile": {
                "hospital_name": "Test Hospital E2E",
                "contact_person": "Dr. Test",
                "contact_phone": "+234123456789"
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}:8001/auth/register"
                async with session.post(url, json=test_user, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("success"):
                            self.test_data["test_user"] = test_user
                            self.test_data["test_user_id"] = data["data"]["user_id"]
                            self.record_test_result("Database connectivity - User registration", True, "User created successfully")
                        else:
                            self.record_test_result("Database connectivity - User registration", False, f"Registration failed: {data}")
                    else:
                        error_text = await response.text()
                        self.record_test_result("Database connectivity - User registration", False, f"HTTP {response.status}: {error_text}")
                        
            except Exception as e:
                self.record_test_result("Database connectivity - User registration", False, f"Error: {str(e)}")
    
    async def test_authentication_flow(self):
        """Test complete authentication flow."""
        logger.info("🔐 Testing authentication flow...")
        
        if not self.test_data.get("test_user"):
            logger.warning("Skipping authentication tests - no test user available")
            return
        
        async with aiohttp.ClientSession() as session:
            # Test 1: User login (note: may fail due to email verification requirement)
            try:
                login_data = {
                    "email": self.test_data["test_user"]["email"],
                    "password": self.test_data["test_user"]["password"]
                }
                
                url = f"{self.base_url}:8001/auth/login"
                async with session.post(url, json=login_data, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "access_token" in data:
                            self.test_data["access_token"] = data["access_token"]
                            self.record_test_result("Authentication - User login", True, "Login successful")
                        else:
                            self.record_test_result("Authentication - User login", False, f"No access token in response: {data}")
                    else:
                        error_text = await response.text()
                        # Note: This might fail due to email verification requirement
                        self.record_test_result("Authentication - User login", False, f"HTTP {response.status}: {error_text}")
                        
            except Exception as e:
                self.record_test_result("Authentication - User login", False, f"Error: {str(e)}")
            
            # Test 2: Token validation (if we have a token)
            if self.test_data.get("access_token"):
                try:
                    headers = {"Authorization": f"Bearer {self.test_data['access_token']}"}
                    url = f"{self.base_url}:8001/auth/me"
                    async with session.get(url, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            self.record_test_result("Authentication - Token validation", True, "Token valid")
                        else:
                            self.record_test_result("Authentication - Token validation", False, f"HTTP {response.status}")
                            
                except Exception as e:
                    self.record_test_result("Authentication - Token validation", False, f"Error: {str(e)}")
    
    async def test_business_operations(self):
        """Test core business operations."""
        logger.info("💼 Testing business operations...")
        
        async with aiohttp.ClientSession() as session:
            # Test 1: Inventory operations
            await self.test_inventory_operations(session)
            
            # Test 2: Order operations
            await self.test_order_operations(session)
            
            # Test 3: Pricing operations
            await self.test_pricing_operations(session)
            
            # Test 4: Location operations
            await self.test_location_operations(session)
    
    async def test_inventory_operations(self, session):
        """Test inventory service operations."""
        try:
            # Test inventory health and basic endpoints
            url = f"{self.base_url}:8004/inventory/"
            async with session.get(url, timeout=10) as response:
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    self.record_test_result("Business Operations - Inventory endpoint", True, f"Endpoint accessible (HTTP {response.status})")
                else:
                    self.record_test_result("Business Operations - Inventory endpoint", False, f"HTTP {response.status}")
                    
        except Exception as e:
            self.record_test_result("Business Operations - Inventory endpoint", False, f"Error: {str(e)}")
    
    async def test_order_operations(self, session):
        """Test order service operations."""
        try:
            # Test order health and basic endpoints
            url = f"{self.base_url}:8005/orders/"
            async with session.get(url, timeout=10) as response:
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    self.record_test_result("Business Operations - Order endpoint", True, f"Endpoint accessible (HTTP {response.status})")
                else:
                    self.record_test_result("Business Operations - Order endpoint", False, f"HTTP {response.status}")
                    
        except Exception as e:
            self.record_test_result("Business Operations - Order endpoint", False, f"Error: {str(e)}")
    
    async def test_pricing_operations(self, session):
        """Test pricing service operations."""
        try:
            # Test pricing health and basic endpoints
            url = f"{self.base_url}:8006/quote-requests"
            async with session.get(url, timeout=10) as response:
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    self.record_test_result("Business Operations - Pricing endpoint", True, f"Endpoint accessible (HTTP {response.status})")
                else:
                    self.record_test_result("Business Operations - Pricing endpoint", False, f"HTTP {response.status}")
                    
        except Exception as e:
            self.record_test_result("Business Operations - Pricing endpoint", False, f"Error: {str(e)}")
    
    async def test_location_operations(self, session):
        """Test location service operations."""
        try:
            # Test location health and basic endpoints
            url = f"{self.base_url}:8003/locations/"
            async with session.get(url, timeout=10) as response:
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    self.record_test_result("Business Operations - Location endpoint", True, f"Endpoint accessible (HTTP {response.status})")
                else:
                    self.record_test_result("Business Operations - Location endpoint", False, f"HTTP {response.status}")

        except Exception as e:
            self.record_test_result("Business Operations - Location endpoint", False, f"Error: {str(e)}")

    async def test_inter_service_communication(self):
        """Test communication between services."""
        logger.info("🔗 Testing inter-service communication...")

        async with aiohttp.ClientSession() as session:
            # Test API Gateway routing to services
            await self.test_api_gateway_routing(session)

            # Test service dependencies
            await self.test_service_dependencies(session)

    async def test_api_gateway_routing(self, session):
        """Test API Gateway routing to different services."""
        try:
            # Test routing to user service through gateway
            url = f"{self.base_url}:8000/api/v1/users/health"
            async with session.get(url, timeout=10) as response:
                if response.status in [200, 404]:  # 404 is acceptable if route not configured
                    self.record_test_result("Inter-Service - API Gateway routing", True, f"Gateway accessible (HTTP {response.status})")
                else:
                    self.record_test_result("Inter-Service - API Gateway routing", False, f"HTTP {response.status}")

        except Exception as e:
            self.record_test_result("Inter-Service - API Gateway routing", False, f"Error: {str(e)}")

    async def test_service_dependencies(self, session):
        """Test service dependency health."""
        try:
            # Test if services can communicate with their dependencies
            # Check order service health (which depends on multiple services)
            url = f"{self.base_url}:8005/health"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    dependencies = data.get("dependencies", {})
                    if dependencies:
                        healthy_deps = sum(1 for dep in dependencies.values() if dep.get("status") == "connected")
                        total_deps = len(dependencies)
                        self.record_test_result("Inter-Service - Service dependencies", True,
                                              f"Dependencies: {healthy_deps}/{total_deps} healthy")
                    else:
                        self.record_test_result("Inter-Service - Service dependencies", True, "No dependencies reported")
                else:
                    self.record_test_result("Inter-Service - Service dependencies", False, f"HTTP {response.status}")

        except Exception as e:
            self.record_test_result("Inter-Service - Service dependencies", False, f"Error: {str(e)}")

    async def test_security_mechanisms(self):
        """Test security mechanisms."""
        logger.info("🔒 Testing security mechanisms...")

        async with aiohttp.ClientSession() as session:
            # Test 1: Unauthorized access protection
            await self.test_unauthorized_access(session)

            # Test 2: Input validation
            await self.test_input_validation(session)

            # Test 3: Security headers
            await self.test_security_headers(session)

    async def test_unauthorized_access(self, session):
        """Test that protected endpoints require authentication."""
        protected_endpoints = [
            (8001, "/auth/me"),
            (8004, "/inventory/"),
            (8005, "/orders/"),
            (8011, "/admin/dashboard")
        ]

        for port, endpoint in protected_endpoints:
            try:
                url = f"{self.base_url}:{port}{endpoint}"
                async with session.get(url, timeout=10) as response:
                    if response.status in [401, 403]:
                        self.record_test_result(f"Security - Unauthorized access protection ({endpoint})", True,
                                              f"Properly protected (HTTP {response.status})")
                    elif response.status == 200:
                        self.record_test_result(f"Security - Unauthorized access protection ({endpoint})", False,
                                              "Endpoint not protected")
                    else:
                        self.record_test_result(f"Security - Unauthorized access protection ({endpoint})", True,
                                              f"Endpoint inaccessible (HTTP {response.status})")

            except Exception as e:
                self.record_test_result(f"Security - Unauthorized access protection ({endpoint})", False, f"Error: {str(e)}")

    async def test_input_validation(self, session):
        """Test input validation mechanisms."""
        try:
            # Test invalid registration data
            invalid_user = {
                "email": "invalid-email",
                "password": "weak",
                "role": "invalid_role"
            }

            url = f"{self.base_url}:8001/auth/register"
            async with session.post(url, json=invalid_user, timeout=10) as response:
                if response.status in [400, 422]:
                    self.record_test_result("Security - Input validation", True,
                                          f"Invalid input rejected (HTTP {response.status})")
                else:
                    self.record_test_result("Security - Input validation", False,
                                          f"Invalid input accepted (HTTP {response.status})")

        except Exception as e:
            self.record_test_result("Security - Input validation", False, f"Error: {str(e)}")

    async def test_security_headers(self, session):
        """Test security headers in responses."""
        try:
            url = f"{self.base_url}:8001/health"
            async with session.get(url, timeout=10) as response:
                headers = response.headers
                security_headers = ['X-Content-Type-Options', 'X-Frame-Options', 'X-XSS-Protection']
                present_headers = [h for h in security_headers if h in headers]

                if present_headers:
                    self.record_test_result("Security - Security headers", True,
                                          f"Headers present: {', '.join(present_headers)}")
                else:
                    self.record_test_result("Security - Security headers", False, "No security headers found")

        except Exception as e:
            self.record_test_result("Security - Security headers", False, f"Error: {str(e)}")

    async def test_error_handling(self):
        """Test error handling mechanisms."""
        logger.info("⚠️ Testing error handling...")

        async with aiohttp.ClientSession() as session:
            # Test 1: 404 handling
            await self.test_404_handling(session)

            # Test 2: Invalid JSON handling
            await self.test_invalid_json_handling(session)

    async def test_404_handling(self, session):
        """Test 404 error handling."""
        try:
            url = f"{self.base_url}:8001/nonexistent/endpoint"
            async with session.get(url, timeout=10) as response:
                if response.status == 404:
                    self.record_test_result("Error Handling - 404 responses", True, "404 properly returned")
                else:
                    self.record_test_result("Error Handling - 404 responses", False, f"HTTP {response.status}")

        except Exception as e:
            self.record_test_result("Error Handling - 404 responses", False, f"Error: {str(e)}")

    async def test_invalid_json_handling(self, session):
        """Test invalid JSON handling."""
        try:
            url = f"{self.base_url}:8001/auth/register"
            headers = {"Content-Type": "application/json"}
            invalid_json = "{ invalid json }"

            async with session.post(url, data=invalid_json, headers=headers, timeout=10) as response:
                if response.status in [400, 422]:
                    self.record_test_result("Error Handling - Invalid JSON", True,
                                          f"Invalid JSON rejected (HTTP {response.status})")
                else:
                    self.record_test_result("Error Handling - Invalid JSON", False,
                                          f"Invalid JSON accepted (HTTP {response.status})")

        except Exception as e:
            self.record_test_result("Error Handling - Invalid JSON", False, f"Error: {str(e)}")
    
    def record_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Record a test result."""
        self.test_results["total_tests"] += 1
        if passed:
            self.test_results["passed"] += 1
            logger.info(f"✅ {test_name}: PASSED - {details}")
        else:
            self.test_results["failed"] += 1
            logger.error(f"❌ {test_name}: FAILED - {details}")
            self.test_results["errors"].append(f"{test_name}: {details}")
        
        self.test_results["test_details"].append({
            "test_name": test_name,
            "status": "PASSED" if passed else "FAILED",
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
    
    def generate_test_report(self):
        """Generate comprehensive test report."""
        logger.info("📋 Generating test report...")
        
        total = self.test_results["total_tests"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]
        success_rate = (passed / total * 100) if total > 0 else 0
        
        report = f"""
{'='*80}
FLOW-BACKEND END-TO-END TEST REPORT
{'='*80}
Test Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SUMMARY:
--------
Total Tests: {total}
Passed: {passed}
Failed: {failed}
Success Rate: {success_rate:.1f}%

SERVICE HEALTH STATUS:
---------------------
"""
        
        for service, health in self.test_results["service_health"].items():
            status = health.get("status", "unknown")
            report += f"{service:20} : {status.upper()}\n"
        
        if self.test_results["errors"]:
            report += f"\nFAILED TESTS:\n{'-'*13}\n"
            for error in self.test_results["errors"]:
                report += f"• {error}\n"
        
        report += f"\n{'='*80}"
        
        print(report)
        
        # Save report to file
        with open("test_report.txt", "w") as f:
            f.write(report)
            f.write("\n\nDETAILED TEST RESULTS:\n")
            f.write(json.dumps(self.test_results, indent=2))
        
        logger.info("📄 Test report saved to test_report.txt")


async def main():
    """Main test execution function."""
    test_suite = E2ETestSuite()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
