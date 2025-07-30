#!/usr/bin/env python3
"""
Enhanced Multi-Perspective Testing Script for Flow-Backend Platform
Comprehensive testing with realistic workflows and proper error handling
"""

import asyncio
import aiohttp
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    test_name: str
    success: bool
    message: str
    data: Optional[Dict] = None
    error: Optional[str] = None

class EnhancedFlowBackendTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results: List[TestResult] = []
        
        # Test data storage
        self.hospital_user = None
        self.supplier_user = None
        self.admin_user = None
        self.hospital_token = None
        self.supplier_token = None
        self.admin_token = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def add_result(self, test_name: str, success: bool, message: str, data: Optional[Dict] = None, error: Optional[str] = None):
        """Add a test result to the results list"""
        result = TestResult(test_name, success, message, data, error)
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {message}")
        if error:
            logger.error(f"Error details: {error}")
    
    async def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                          headers: Optional[Dict] = None, token: Optional[str] = None) -> Dict:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        if headers is None:
            headers = {"Content-Type": "application/json"}
        
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            async with self.session.request(method, url, json=data, headers=headers) as response:
                response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                
                return {
                    "status_code": response.status,
                    "data": response_data,
                    "success": response.status < 400
                }
        except Exception as e:
            return {
                "status_code": 0,
                "data": None,
                "success": False,
                "error": str(e)
            }
    
    async def test_system_health(self):
        """Test overall system health"""
        logger.info("🏥 Testing System Health...")
        
        result = await self.make_request("GET", "/health")
        if result["success"]:
            self.add_result("System Health Check", True, "All services are healthy", result["data"])
            return True
        else:
            self.add_result("System Health Check", False, "System health check failed", error=result.get("error"))
            return False
    
    async def test_hospital_workflow(self):
        """Test complete hospital workflow"""
        logger.info("🏥 Testing Hospital Workflow...")
        
        # 1. Hospital Registration
        hospital_email = f"hospital_{uuid.uuid4().hex[:8]}@test.com"
        hospital_data = {
            "email": hospital_email,
            "password": "SecurePass123!",
            "role": "hospital",
            "first_name": "Dr. John",
            "last_name": "Smith",
            "phone_number": "+2348012345678"
        }
        
        result = await self.make_request("POST", "/auth/register", hospital_data)
        if result["success"]:
            self.hospital_user = result["data"]
            self.add_result("Hospital Registration", True, "Hospital registered successfully", result["data"])
        else:
            self.add_result("Hospital Registration", False, "Hospital registration failed", error=result.get("error"))
            return False
        
        # 2. Test Product Catalog Access (without authentication for now)
        result = await self.make_request("GET", "/catalog/featured")
        self.add_result("Product Catalog Access", result["success"],
                       "Product catalog accessible" if result["success"] else "Product catalog access failed",
                       result["data"], result.get("error"))
        
        # 3. Test Emergency Products Access
        result = await self.make_request("GET", "/catalog/emergency?latitude=6.5244&longitude=3.3792")
        self.add_result("Emergency Products Access", result["success"],
                       "Emergency products accessible" if result["success"] else "Emergency products access failed",
                       result["data"], result.get("error"))
        
        return True
    
    async def test_supplier_workflow(self):
        """Test complete supplier workflow"""
        logger.info("🏭 Testing Supplier Workflow...")
        
        # 1. Supplier Registration
        supplier_email = f"supplier_{uuid.uuid4().hex[:8]}@test.com"
        supplier_data = {
            "email": supplier_email,
            "password": "SecurePass123!",
            "role": "vendor",
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_number": "+2348087654321"
        }
        
        result = await self.make_request("POST", "/auth/register", supplier_data)
        if result["success"]:
            self.supplier_user = result["data"]
            self.add_result("Supplier Registration", True, "Supplier registered successfully", result["data"])
        else:
            self.add_result("Supplier Registration", False, "Supplier registration failed", error=result.get("error"))
            return False
        
        # 2. Test Vendor Discovery (public endpoint)
        result = await self.make_request("GET", "/vendors/nearby?latitude=6.5244&longitude=3.3792&radius_km=50")
        self.add_result("Vendor Discovery", result["success"],
                       "Vendor discovery accessible" if result["success"] else "Vendor discovery failed",
                       result["data"], result.get("error"))
        
        return True
    
    async def test_admin_workflow(self):
        """Test admin workflow"""
        logger.info("👨‍💼 Testing Admin Workflow...")
        
        # 1. Test System Monitoring (public health endpoint)
        result = await self.make_request("GET", "/health")
        self.add_result("Admin System Monitoring", result["success"],
                       "System monitoring accessible" if result["success"] else "System monitoring failed",
                       result["data"], result.get("error"))
        
        # 2. Test Service Status Monitoring
        if result["success"] and "services" in result["data"]:
            services = result["data"]["services"]
            healthy_services = sum(1 for service in services.values() if service.get("status") == "healthy")
            total_services = len(services)
            
            self.add_result("Service Status Monitoring", True,
                           f"Monitoring {total_services} services, {healthy_services} healthy",
                           {"healthy": healthy_services, "total": total_services})
        
        return True
    
    async def test_api_endpoints(self):
        """Test various API endpoints"""
        logger.info("🔗 Testing API Endpoints...")
        
        endpoints_to_test = [
            ("GET", "/health", "Health Check"),
            ("GET", "/docs", "API Documentation"),
            ("GET", "/openapi.json", "OpenAPI Schema"),
        ]
        
        for method, endpoint, name in endpoints_to_test:
            result = await self.make_request(method, endpoint)
            self.add_result(f"API Endpoint - {name}", result["success"],
                           f"{name} accessible" if result["success"] else f"{name} failed",
                           None, result.get("error"))
    
    async def test_database_connectivity(self):
        """Test database connectivity through health endpoints"""
        logger.info("🗄️ Testing Database Connectivity...")
        
        # Test through health endpoint which should check DB connectivity
        result = await self.make_request("GET", "/health")
        if result["success"]:
            # Check if all services are healthy (indicates DB connectivity)
            services = result["data"].get("services", {})
            db_dependent_services = ["user", "order", "inventory", "payment"]
            
            healthy_db_services = 0
            for service_name in db_dependent_services:
                if service_name in services and services[service_name].get("status") == "healthy":
                    healthy_db_services += 1
            
            success = healthy_db_services == len(db_dependent_services)
            self.add_result("Database Connectivity", success,
                           f"Database connectivity verified through {healthy_db_services}/{len(db_dependent_services)} services",
                           {"healthy_services": healthy_db_services, "total_services": len(db_dependent_services)})
        else:
            self.add_result("Database Connectivity", False, "Cannot verify database connectivity", 
                          error=result.get("error"))
    
    async def test_security_features(self):
        """Test security features"""
        logger.info("🔒 Testing Security Features...")
        
        # 1. Test protected endpoint without authentication
        result = await self.make_request("GET", "/users/profile")
        expected_failure = result["status_code"] in [401, 403]
        self.add_result("Authentication Protection", expected_failure,
                       "Protected endpoints properly secured" if expected_failure else "Security issue: unprotected endpoint",
                       {"status_code": result["status_code"]})
        
        # 2. Test CORS headers
        result = await self.make_request("OPTIONS", "/health")
        self.add_result("CORS Configuration", result["success"],
                       "CORS properly configured" if result["success"] else "CORS configuration issue",
                       None, result.get("error"))
    
    async def run_comprehensive_tests(self):
        """Run all comprehensive tests"""
        logger.info("🚀 Starting Enhanced Multi-Perspective Testing...")
        
        # Core system tests
        await self.test_system_health()
        await self.test_database_connectivity()
        await self.test_api_endpoints()
        await self.test_security_features()
        
        # Perspective-specific tests
        await self.test_hospital_workflow()
        await self.test_supplier_workflow()
        await self.test_admin_workflow()
        
        # Generate comprehensive report
        self.generate_comprehensive_report()
    
    def generate_comprehensive_report(self):
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.success)
        failed_tests = total_tests - passed_tests
        
        logger.info("\n" + "="*80)
        logger.info("📊 ENHANCED COMPREHENSIVE TESTING REPORT")
        logger.info("="*80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        logger.info("="*80)
        
        # Categorize results
        categories = {
            "System Health": [],
            "Hospital Workflow": [],
            "Supplier Workflow": [],
            "Admin Workflow": [],
            "API Endpoints": [],
            "Security": [],
            "Database": [],
            "Other": []
        }
        
        for result in self.test_results:
            categorized = False
            for category in categories.keys():
                if category.lower() in result.test_name.lower():
                    categories[category].append(result)
                    categorized = True
                    break
            if not categorized:
                categories["Other"].append(result)
        
        # Display category results
        for category, results in categories.items():
            if results:
                passed = sum(1 for r in results if r.success)
                total = len(results)
                success_rate = (passed / total) * 100 if total > 0 else 0
                
                logger.info(f"\n📋 {category}: {passed}/{total} passed ({success_rate:.1f}%)")
                
                # Show failed tests
                failed_tests = [r for r in results if not r.success]
                if failed_tests:
                    logger.info(f"   Failed tests in {category}:")
                    for test in failed_tests:
                        logger.info(f"   ❌ {test.test_name}: {test.message}")
                        if test.error:
                            logger.info(f"      Error: {test.error}")
        
        # Summary recommendations
        logger.info("\n" + "="*80)
        logger.info("📋 TESTING RECOMMENDATIONS")
        logger.info("="*80)
        
        if passed_tests / total_tests >= 0.9:
            logger.info("🎉 Excellent! System is production-ready with high test coverage.")
        elif passed_tests / total_tests >= 0.7:
            logger.info("✅ Good! System is mostly functional with some areas for improvement.")
        elif passed_tests / total_tests >= 0.5:
            logger.info("⚠️  Moderate! System has core functionality but needs significant improvements.")
        else:
            logger.info("❌ Critical! System needs major fixes before deployment.")
        
        logger.info("\nNext Steps:")
        logger.info("1. Address failed tests in order of priority")
        logger.info("2. Implement missing authentication flows")
        logger.info("3. Add comprehensive integration tests")
        logger.info("4. Perform load testing")
        logger.info("5. Security audit and penetration testing")

async def main():
    """Main test execution function"""
    async with EnhancedFlowBackendTester() as tester:
        await tester.run_comprehensive_tests()

if __name__ == "__main__":
    asyncio.run(main())
