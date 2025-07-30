#!/usr/bin/env python3
"""
Final Validation Test for Flow-Backend Platform
Tests all implemented fixes and improvements
"""

import asyncio
import aiohttp
import json
import uuid
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FinalValidationTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, endpoint: str, data: dict = None, headers: dict = None) -> dict:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        if headers is None:
            headers = {"Content-Type": "application/json"}
        
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
    
    def log_test(self, test_name: str, success: bool, message: str, data: dict = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {message}")
        self.test_results.append({"test": test_name, "success": success, "message": message, "data": data})
    
    async def test_optimized_health_check(self):
        """Test the optimized health check performance"""
        logger.info("🚀 Testing Optimized Health Check Performance...")
        
        start_time = datetime.now()
        result = await self.make_request("GET", "/health")
        end_time = datetime.now()
        
        response_time = (end_time - start_time).total_seconds()
        is_fast = response_time < 1.0  # Should be much faster now
        
        self.log_test("Optimized Health Check", is_fast and result["success"],
                     f"Health check completed in {response_time:.3f}s {'(Fast!)' if is_fast else '(Still slow)'}",
                     {"response_time": response_time, "services": result["data"].get("services", {}) if result["success"] else None})
    
    async def test_public_endpoints(self):
        """Test new public endpoints that don't require authentication"""
        logger.info("🌐 Testing Public Endpoints...")
        
        # Test public catalog
        result = await self.make_request("GET", "/catalog/public/featured?limit=5")
        self.log_test("Public Featured Products", result["success"],
                     "Public catalog accessible" if result["success"] else "Public catalog failed",
                     result["data"] if result["success"] else {"error": result.get("error")})
        
        # Test public vendor discovery
        result = await self.make_request("GET", "/vendors/public/nearby?latitude=6.5244&longitude=3.3792&radius_km=50")
        self.log_test("Public Vendor Discovery", result["success"],
                     "Public vendor discovery accessible" if result["success"] else "Public vendor discovery failed",
                     result["data"] if result["success"] else {"error": result.get("error")})
    
    async def test_authentication_fixes(self):
        """Test authentication fixes including development bypass"""
        logger.info("🔐 Testing Authentication Fixes...")
        
        # Test user registration
        hospital_email = f"test_hospital_{uuid.uuid4().hex[:8]}@test.com"
        hospital_data = {
            "email": hospital_email,
            "password": "SecurePass123!",
            "role": "hospital",
            "first_name": "Test",
            "last_name": "Hospital",
            "phone_number": "+2348012345678"
        }
        
        result = await self.make_request("POST", "/auth/register", hospital_data)
        if result["success"]:
            self.log_test("Hospital Registration", True, "Hospital registration successful", result["data"])
            
            # Test development email verification
            verify_result = await self.make_request("POST", "/dev/verify-user-email", {"email": hospital_email})
            self.log_test("Development Email Verification", verify_result["success"],
                         "Email verification bypass working" if verify_result["success"] else "Email verification bypass failed",
                         verify_result["data"] if verify_result["success"] else {"error": verify_result.get("error")})
            
            # Test login with development bypass
            login_data = {"email": hospital_email, "password": "SecurePass123!"}
            login_result = await self.make_request("POST", "/auth/login", login_data)
            
            if login_result["success"] and "access_token" in login_result["data"]:
                self.log_test("Hospital Login with Dev Bypass", True, "Login successful with development bypass", 
                             {"has_token": True})
                
                # Test hospital profile creation
                token = login_result["data"]["access_token"]
                profile_data = {
                    "hospital_name": "Test General Hospital",
                    "registration_number": "HRN123456",
                    "license_number": "HLN789012",
                    "contact_person": "Dr. Test",
                    "contact_phone": "+2348012345678",
                    "bed_capacity": "200",
                    "hospital_type": "general"
                }
                
                profile_result = await self.make_request("POST", "/hospital-profiles", profile_data,
                                                       headers={"Authorization": f"Bearer {token}"})
                self.log_test("Hospital Profile Creation", profile_result["success"],
                             "Hospital profile created" if profile_result["success"] else "Hospital profile creation failed",
                             profile_result["data"] if profile_result["success"] else {"error": profile_result.get("error")})
                
                # Test authenticated catalog access
                catalog_result = await self.make_request("GET", "/catalog/featured?limit=5",
                                                       headers={"Authorization": f"Bearer {token}"})
                self.log_test("Authenticated Catalog Access", catalog_result["success"],
                             "Authenticated catalog access working" if catalog_result["success"] else "Authenticated catalog access failed",
                             catalog_result["data"] if catalog_result["success"] else {"error": catalog_result.get("error")})
            else:
                self.log_test("Hospital Login with Dev Bypass", False, "Login failed even with development bypass",
                             {"error": login_result.get("error")})
        else:
            self.log_test("Hospital Registration", False, "Hospital registration failed", 
                         {"error": result.get("error")})
    
    async def test_error_handling_improvements(self):
        """Test improved error handling"""
        logger.info("⚠️ Testing Error Handling Improvements...")
        
        # Test 404 handling
        result = await self.make_request("GET", "/nonexistent-endpoint")
        has_proper_error_format = (result["status_code"] == 404 and 
                                 isinstance(result["data"], dict) and 
                                 "error" in result["data"])
        
        self.log_test("404 Error Handling", has_proper_error_format,
                     "404 errors properly formatted" if has_proper_error_format else "404 error format needs improvement",
                     result["data"])
        
        # Test validation error handling
        invalid_data = {"email": "invalid-email", "password": "123"}
        result = await self.make_request("POST", "/auth/register", invalid_data)
        has_validation_error = result["status_code"] in [400, 422]
        
        self.log_test("Validation Error Handling", has_validation_error,
                     "Validation errors properly handled" if has_validation_error else "Validation error handling needs improvement",
                     {"status_code": result["status_code"]})
    
    async def test_cors_improvements(self):
        """Test CORS improvements"""
        logger.info("🌐 Testing CORS Improvements...")
        
        # Test OPTIONS request
        result = await self.make_request("OPTIONS", "/health")
        self.log_test("CORS OPTIONS Support", result["success"],
                     "OPTIONS requests supported" if result["success"] else "OPTIONS requests not supported",
                     {"status_code": result["status_code"]})
    
    async def run_final_validation(self):
        """Run all final validation tests"""
        logger.info("🎯 Starting Final Validation Testing...")
        
        await self.test_optimized_health_check()
        await self.test_public_endpoints()
        await self.test_authentication_fixes()
        await self.test_error_handling_improvements()
        await self.test_cors_improvements()
        
        # Generate final report
        self.generate_final_report()
    
    def generate_final_report(self):
        """Generate final validation report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        logger.info("\n" + "="*80)
        logger.info("🎯 FINAL VALIDATION REPORT")
        logger.info("="*80)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        logger.info("="*80)
        
        # Show failed tests
        failed_tests_list = [r for r in self.test_results if not r["success"]]
        if failed_tests_list:
            logger.info("\n❌ Failed Tests:")
            for test in failed_tests_list:
                logger.info(f"   • {test['test']}: {test['message']}")
        
        # Show improvements
        improvements = []
        for test in self.test_results:
            if test["success"]:
                if "Fast" in test["message"] or "successful" in test["message"]:
                    improvements.append(test["test"])
        
        if improvements:
            logger.info(f"\n✅ Key Improvements Validated:")
            for improvement in improvements:
                logger.info(f"   • {improvement}")
        
        # Final assessment
        if passed_tests / total_tests >= 0.9:
            logger.info("\n🎉 EXCELLENT! All major fixes implemented and working correctly.")
        elif passed_tests / total_tests >= 0.8:
            logger.info("\n✅ GOOD! Most fixes implemented successfully with minor issues remaining.")
        elif passed_tests / total_tests >= 0.7:
            logger.info("\n⚠️ MODERATE! Some fixes working but more work needed.")
        else:
            logger.info("\n❌ CRITICAL! Major issues still present.")

async def main():
    """Main test execution function"""
    async with FinalValidationTester() as tester:
        await tester.run_final_validation()

if __name__ == "__main__":
    asyncio.run(main())
