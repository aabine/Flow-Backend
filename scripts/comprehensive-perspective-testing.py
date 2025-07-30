#!/usr/bin/env python3
"""
Comprehensive Multi-Perspective Testing Script for Flow-Backend Platform
Tests Hospital, Supplier, and Admin perspectives with realistic workflows
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

class FlowBackendTester:
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
    
    async def test_service_health(self):
        """Test health endpoints for all services"""
        logger.info("🏥 Testing Service Health Endpoints...")

        # Test API Gateway health (which includes all services)
        result = await self.make_request("GET", "/health")
        if result["success"]:
            self.add_result("API Gateway Health", True, "API Gateway is healthy", result["data"])

            # Parse service statuses from API Gateway response
            if "services" in result["data"]:
                services_data = result["data"]["services"]
                healthy_services = 0
                total_services = len(services_data)

                for service_name, service_info in services_data.items():
                    if service_info.get("status") == "healthy":
                        self.add_result(f"Service Health - {service_name.title()}", True,
                                      f"Service is healthy (response time: {service_info.get('response_time', 'N/A')}s)")
                        healthy_services += 1
                    else:
                        self.add_result(f"Service Health - {service_name.title()}", False,
                                      f"Service is unhealthy: {service_info}")

                overall_health = healthy_services == total_services
                self.add_result("Overall System Health", overall_health,
                               f"{healthy_services}/{total_services} services healthy")
                return overall_health
        else:
            self.add_result("API Gateway Health", False, "API Gateway is unhealthy", error=result.get("error"))
            return False
        
        healthy_services = 0
        for service_name, endpoint in services:
            result = await self.make_request("GET", endpoint)
            
            if result["success"]:
                self.add_result(f"Health Check - {service_name}", True, "Service is healthy", result["data"])
                healthy_services += 1
            else:
                self.add_result(f"Health Check - {service_name}", False, 
                              f"Service unhealthy (Status: {result['status_code']})", 
                              error=result.get("error"))
        
        overall_health = healthy_services == len(services)
        self.add_result("Overall System Health", overall_health, 
                       f"{healthy_services}/{len(services)} services healthy")
        
        return overall_health
    
    async def test_hospital_perspective(self):
        """Test complete hospital user workflow"""
        logger.info("🏥 Testing Hospital Perspective...")
        
        # 1. Hospital User Registration
        hospital_data = {
            "email": f"hospital_{uuid.uuid4().hex[:8]}@test.com",
            "password": "SecurePass123!",
            "role": "hospital",
            "first_name": "Dr. John",
            "last_name": "Smith",
            "phone_number": "+2348012345678"
        }

        result = await self.make_request("POST", "/auth/register", hospital_data)
        if result["success"]:
            self.hospital_user = result["data"]
            self.add_result("Hospital Registration", True, "Hospital user registered successfully", result["data"])
        else:
            self.add_result("Hospital Registration", False, "Failed to register hospital user", 
                          error=result.get("error"))
            return False
        
        # 2. Hospital Login
        login_data = {
            "email": hospital_data["email"],
            "password": hospital_data["password"]
        }

        result = await self.make_request("POST", "/auth/login", login_data)
        if result["success"] and "access_token" in result["data"]:
            self.hospital_token = result["data"]["access_token"]
            self.add_result("Hospital Login", True, "Hospital login successful", result["data"])
        else:
            self.add_result("Hospital Login", False, "Hospital login failed", error=result.get("error"))
            return False

        # 2.5. Create Hospital Profile
        hospital_profile_data = {
            "hospital_name": "Test General Hospital",
            "registration_number": "HRN123456",
            "license_number": "HLN789012",
            "contact_person": "Dr. John Smith",
            "contact_phone": "+2348012345678",
            "bed_capacity": "200",
            "hospital_type": "general"
        }

        result = await self.make_request("POST", "/users/hospital-profiles", hospital_profile_data,
                                       token=self.hospital_token)
        self.add_result("Hospital Profile Creation", result["success"],
                       "Hospital profile created" if result["success"] else "Failed to create hospital profile",
                       result["data"], result.get("error"))
        
        # 3. Browse Product Catalog
        catalog_params = {
            "latitude": 6.5244,
            "longitude": 3.3792,
            "max_distance_km": 50,
            "page": 1,
            "page_size": 10
        }
        
        result = await self.make_request("GET", "/catalog/nearby", headers={"Authorization": f"Bearer {self.hospital_token}"})
        self.add_result("Product Catalog Browse", result["success"], 
                       "Product catalog browsed" if result["success"] else "Failed to browse catalog",
                       result["data"], result.get("error"))
        
        # 4. Check Real-time Inventory
        availability_data = {
            "vendor_id": str(uuid.uuid4()),
            "cylinder_size": "4 meter",
            "quantity": 5
        }
        
        result = await self.make_request("POST", "/catalog/availability/check", availability_data, 
                                       token=self.hospital_token)
        self.add_result("Inventory Availability Check", result["success"],
                       "Inventory check completed" if result["success"] else "Inventory check failed",
                       result["data"], result.get("error"))
        
        # 5. Emergency Order Test
        emergency_result = await self.make_request("GET", "/catalog/emergency", 
                                                 headers={"Authorization": f"Bearer {self.hospital_token}"})
        self.add_result("Emergency Products Access", emergency_result["success"],
                       "Emergency products accessed" if emergency_result["success"] else "Emergency access failed",
                       emergency_result["data"], emergency_result.get("error"))
        
        return True
    
    async def test_supplier_perspective(self):
        """Test complete supplier user workflow"""
        logger.info("🏭 Testing Supplier Perspective...")
        
        # 1. Supplier User Registration
        supplier_data = {
            "email": f"supplier_{uuid.uuid4().hex[:8]}@test.com",
            "password": "SecurePass123!",
            "role": "vendor",
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_number": "+2348087654321"
        }

        result = await self.make_request("POST", "/auth/register", supplier_data)
        if result["success"]:
            self.supplier_user = result["data"]
            self.add_result("Supplier Registration", True, "Supplier user registered successfully", result["data"])
        else:
            self.add_result("Supplier Registration", False, "Failed to register supplier user", 
                          error=result.get("error"))
            return False
        
        # 2. Supplier Login
        login_data = {
            "email": supplier_data["email"],
            "password": supplier_data["password"]
        }
        
        result = await self.make_request("POST", "/auth/login", login_data)
        if result["success"] and "access_token" in result["data"]:
            self.supplier_token = result["data"]["access_token"]
            self.add_result("Supplier Login", True, "Supplier login successful", result["data"])
        else:
            self.add_result("Supplier Login", False, "Supplier login failed", error=result.get("error"))
            return False

        # 2.5. Create Vendor Profile
        vendor_profile_data = {
            "business_name": "Test Medical Supplies Ltd",
            "registration_number": "RC123456",
            "tax_identification_number": "TIN789012",
            "contact_person": "Jane Doe",
            "contact_phone": "+2348087654321",
            "business_address": "123 Medical Street, Lagos",
            "delivery_radius_km": 50.0,
            "emergency_service": True,
            "minimum_order_value": 10000.0
        }

        result = await self.make_request("POST", "/users/vendor-profiles", vendor_profile_data,
                                       token=self.supplier_token)
        self.add_result("Vendor Profile Creation", result["success"],
                       "Vendor profile created" if result["success"] else "Failed to create vendor profile",
                       result["data"], result.get("error"))
        
        # 3. Supplier KYC Submission
        kyc_data = {
            "user_id": self.supplier_user.get("id", str(uuid.uuid4())),
            "business_name": supplier_data["vendor_profile"]["business_name"],
            "registration_number": supplier_data["vendor_profile"]["registration_number"],
            "tax_identification_number": supplier_data["vendor_profile"]["tax_identification_number"],
            "contact_person": supplier_data["vendor_profile"]["contact_person"],
            "contact_phone": supplier_data["vendor_profile"]["contact_phone"],
            "business_address": supplier_data["vendor_profile"]["business_address"]
        }
        
        result = await self.make_request("POST", "/suppliers/onboarding/kyc", kyc_data, token=self.supplier_token)
        self.add_result("Supplier KYC Submission", result["success"],
                       "KYC submitted successfully" if result["success"] else "KYC submission failed",
                       result["data"], result.get("error"))
        
        # 4. Inventory Management Test
        inventory_data = {
            "location_name": "Main Warehouse",
            "address": "456 Warehouse Ave, Lagos",
            "city": "Lagos",
            "state": "Lagos",
            "country": "Nigeria",
            "latitude": 6.5244,
            "longitude": 3.3792
        }
        
        result = await self.make_request("POST", "/inventory/", inventory_data, token=self.supplier_token)
        self.add_result("Inventory Location Creation", result["success"],
                       "Inventory location created" if result["success"] else "Failed to create inventory location",
                       result["data"], result.get("error"))
        
        return True
    
    async def test_admin_perspective(self):
        """Test admin user workflow"""
        logger.info("👨‍💼 Testing Admin Perspective...")
        
        # Note: Admin users typically need to be created through a different process
        # For testing, we'll test admin endpoints that don't require authentication first
        
        # 1. System Health Monitoring
        result = await self.make_request("GET", "/admin/system-health")
        self.add_result("Admin System Health Check", result["success"],
                       "System health retrieved" if result["success"] else "Failed to get system health",
                       result["data"], result.get("error"))
        
        # 2. Analytics Dashboard
        result = await self.make_request("GET", "/admin/dashboard")
        self.add_result("Admin Dashboard Access", result["success"],
                       "Dashboard accessed" if result["success"] else "Dashboard access failed",
                       result["data"], result.get("error"))
        
        # 3. User Management (without auth for now)
        result = await self.make_request("GET", "/admin/users")
        self.add_result("Admin User Management", result["success"],
                       "User list retrieved" if result["success"] else "Failed to get user list",
                       result["data"], result.get("error"))
        
        return True
    
    async def run_all_tests(self):
        """Run all test suites"""
        logger.info("🚀 Starting Comprehensive Multi-Perspective Testing...")
        
        # Test service health first
        health_ok = await self.test_service_health()
        
        if not health_ok:
            logger.warning("⚠️ Some services are unhealthy, but continuing with tests...")
        
        # Run perspective tests
        await self.test_hospital_perspective()
        await self.test_supplier_perspective()
        await self.test_admin_perspective()
        
        # Generate summary report
        self.generate_summary_report()
    
    def generate_summary_report(self):
        """Generate and display test summary report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result.success)
        failed_tests = total_tests - passed_tests
        
        logger.info("\n" + "="*80)
        logger.info("📊 COMPREHENSIVE TESTING SUMMARY REPORT")
        logger.info("="*80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        logger.info("="*80)
        
        # Group results by category
        categories = {}
        for result in self.test_results:
            category = result.test_name.split(" - ")[0] if " - " in result.test_name else "General"
            if category not in categories:
                categories[category] = {"passed": 0, "failed": 0, "tests": []}
            
            if result.success:
                categories[category]["passed"] += 1
            else:
                categories[category]["failed"] += 1
            categories[category]["tests"].append(result)
        
        # Display category summaries
        for category, stats in categories.items():
            total_cat = stats["passed"] + stats["failed"]
            success_rate = (stats["passed"] / total_cat) * 100 if total_cat > 0 else 0
            logger.info(f"\n📋 {category}: {stats['passed']}/{total_cat} passed ({success_rate:.1f}%)")
            
            # Show failed tests
            failed_tests = [test for test in stats["tests"] if not test.success]
            if failed_tests:
                logger.info(f"   Failed tests in {category}:")
                for test in failed_tests:
                    logger.info(f"   ❌ {test.test_name}: {test.message}")
                    if test.error:
                        logger.info(f"      Error: {test.error}")

async def main():
    """Main test execution function"""
    async with FlowBackendTester() as tester:
        await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
