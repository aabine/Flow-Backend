#!/usr/bin/env python3
"""
Integration Workflow Testing for Flow-Backend Platform
Tests end-to-end workflows across multiple perspectives
"""

import asyncio
import aiohttp
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntegrationWorkflowTester:
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
    
    async def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                          headers: Optional[Dict] = None) -> Dict:
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
    
    def log_test_result(self, test_name: str, success: bool, message: str, data: Optional[Dict] = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {message}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "data": data
        })
    
    async def test_service_discovery_workflow(self):
        """Test service discovery and health monitoring workflow"""
        logger.info("🔍 Testing Service Discovery Workflow...")
        
        # 1. Check overall system health
        result = await self.make_request("GET", "/health")
        if result["success"]:
            services = result["data"].get("services", {})
            healthy_count = sum(1 for s in services.values() if s.get("status") == "healthy")
            total_count = len(services)
            
            self.log_test_result("Service Discovery", True, 
                               f"Discovered {total_count} services, {healthy_count} healthy",
                               {"services": list(services.keys()), "healthy_count": healthy_count})
            
            # 2. Test individual service responsiveness
            for service_name, service_info in services.items():
                response_time = service_info.get("response_time", 0)
                is_fast = response_time < 0.1  # Less than 100ms
                
                self.log_test_result(f"Service Performance - {service_name.title()}", is_fast,
                                   f"Response time: {response_time:.3f}s {'(Good)' if is_fast else '(Slow)'}",
                                   {"response_time": response_time})
        else:
            self.log_test_result("Service Discovery", False, "Failed to discover services", 
                               {"error": result.get("error")})
    
    async def test_user_registration_workflow(self):
        """Test user registration workflow for different roles"""
        logger.info("👥 Testing User Registration Workflow...")
        
        roles_to_test = [
            ("hospital", "Hospital User Registration"),
            ("vendor", "Supplier User Registration")
        ]
        
        for role, test_name in roles_to_test:
            user_data = {
                "email": f"{role}_{uuid.uuid4().hex[:8]}@test.com",
                "password": "SecurePass123!",
                "role": role,
                "first_name": "Test",
                "last_name": "User",
                "phone_number": "+2348012345678"
            }
            
            result = await self.make_request("POST", "/auth/register", user_data)
            self.log_test_result(test_name, result["success"],
                               f"{role.title()} registration {'successful' if result['success'] else 'failed'}",
                               result["data"] if result["success"] else {"error": result.get("error")})
    
    async def test_api_documentation_workflow(self):
        """Test API documentation and schema availability"""
        logger.info("📚 Testing API Documentation Workflow...")
        
        doc_endpoints = [
            ("/docs", "Interactive API Documentation"),
            ("/redoc", "ReDoc API Documentation"),
            ("/openapi.json", "OpenAPI Schema")
        ]
        
        for endpoint, name in doc_endpoints:
            result = await self.make_request("GET", endpoint)
            self.log_test_result(f"Documentation - {name}", result["success"],
                               f"{name} {'accessible' if result['success'] else 'not accessible'}",
                               {"status_code": result["status_code"]})
    
    async def test_security_workflow(self):
        """Test security features and protections"""
        logger.info("🔒 Testing Security Workflow...")
        
        # 1. Test authentication requirement on protected endpoints
        protected_endpoints = [
            ("/users/profile", "User Profile"),
            ("/orders", "Orders"),
            ("/inventory", "Inventory")
        ]
        
        for endpoint, name in protected_endpoints:
            result = await self.make_request("GET", endpoint)
            is_protected = result["status_code"] in [401, 403]
            
            self.log_test_result(f"Security - {name} Protection", is_protected,
                               f"{name} endpoint {'properly protected' if is_protected else 'not protected'}",
                               {"status_code": result["status_code"]})
        
        # 2. Test rate limiting (if implemented)
        # This would require multiple rapid requests to test
        
        # 3. Test input validation
        invalid_registration = {
            "email": "invalid-email",
            "password": "123",  # Too short
            "role": "invalid_role"
        }
        
        result = await self.make_request("POST", "/auth/register", invalid_registration)
        validation_works = not result["success"]
        
        self.log_test_result("Security - Input Validation", validation_works,
                           f"Input validation {'working' if validation_works else 'not working'}",
                           {"status_code": result["status_code"]})
    
    async def test_error_handling_workflow(self):
        """Test error handling across the platform"""
        logger.info("⚠️ Testing Error Handling Workflow...")
        
        # 1. Test 404 handling
        result = await self.make_request("GET", "/nonexistent-endpoint")
        handles_404 = result["status_code"] == 404
        
        self.log_test_result("Error Handling - 404", handles_404,
                           f"404 errors {'properly handled' if handles_404 else 'not handled'}",
                           {"status_code": result["status_code"]})
        
        # 2. Test malformed JSON handling
        try:
            async with self.session.post(f"{self.base_url}/auth/register", 
                                       data="invalid json", 
                                       headers={"Content-Type": "application/json"}) as response:
                handles_bad_json = response.status == 400
                
                self.log_test_result("Error Handling - Malformed JSON", handles_bad_json,
                                   f"Malformed JSON {'properly handled' if handles_bad_json else 'not handled'}",
                                   {"status_code": response.status})
        except Exception as e:
            self.log_test_result("Error Handling - Malformed JSON", False,
                               f"Error handling malformed JSON: {str(e)}")
    
    async def test_performance_workflow(self):
        """Test basic performance characteristics"""
        logger.info("⚡ Testing Performance Workflow...")
        
        # Test response times for key endpoints
        performance_endpoints = [
            ("/health", "Health Check", 0.1),  # Should be very fast
            ("/docs", "Documentation", 0.5),   # Can be slower
            ("/openapi.json", "API Schema", 0.3)  # Should be reasonably fast
        ]
        
        for endpoint, name, max_time in performance_endpoints:
            start_time = datetime.now()
            result = await self.make_request("GET", endpoint)
            end_time = datetime.now()
            
            response_time = (end_time - start_time).total_seconds()
            is_fast = response_time <= max_time
            
            self.log_test_result(f"Performance - {name}", is_fast,
                               f"{name} response time: {response_time:.3f}s {'(Good)' if is_fast else '(Slow)'}",
                               {"response_time": response_time, "max_expected": max_time})
    
    async def run_integration_tests(self):
        """Run all integration tests"""
        logger.info("🚀 Starting Integration Workflow Testing...")
        
        # Run all test workflows
        await self.test_service_discovery_workflow()
        await self.test_user_registration_workflow()
        await self.test_api_documentation_workflow()
        await self.test_security_workflow()
        await self.test_error_handling_workflow()
        await self.test_performance_workflow()
        
        # Generate summary report
        self.generate_integration_report()
    
    def generate_integration_report(self):
        """Generate integration test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        logger.info("\n" + "="*80)
        logger.info("📊 INTEGRATION WORKFLOW TESTING REPORT")
        logger.info("="*80)
        logger.info(f"Total Integration Tests: {total_tests}")
        logger.info(f"✅ Passed: {passed_tests}")
        logger.info(f"❌ Failed: {failed_tests}")
        logger.info(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        logger.info("="*80)
        
        # Group by workflow type
        workflows = {}
        for result in self.test_results:
            workflow = result["test"].split(" - ")[0] if " - " in result["test"] else "General"
            if workflow not in workflows:
                workflows[workflow] = {"passed": 0, "failed": 0, "tests": []}
            
            if result["success"]:
                workflows[workflow]["passed"] += 1
            else:
                workflows[workflow]["failed"] += 1
            workflows[workflow]["tests"].append(result)
        
        # Display workflow results
        for workflow, stats in workflows.items():
            total = stats["passed"] + stats["failed"]
            success_rate = (stats["passed"] / total) * 100 if total > 0 else 0
            
            logger.info(f"\n📋 {workflow}: {stats['passed']}/{total} passed ({success_rate:.1f}%)")
            
            # Show failed tests
            failed_tests = [test for test in stats["tests"] if not test["success"]]
            if failed_tests:
                logger.info(f"   Failed tests in {workflow}:")
                for test in failed_tests:
                    logger.info(f"   ❌ {test['test']}: {test['message']}")
        
        # Integration assessment
        logger.info("\n" + "="*80)
        logger.info("📋 INTEGRATION ASSESSMENT")
        logger.info("="*80)
        
        if passed_tests / total_tests >= 0.9:
            logger.info("🎉 Excellent! Platform integration is robust and production-ready.")
        elif passed_tests / total_tests >= 0.8:
            logger.info("✅ Good! Platform integration is solid with minor issues.")
        elif passed_tests / total_tests >= 0.7:
            logger.info("⚠️  Moderate! Platform integration needs some improvements.")
        else:
            logger.info("❌ Critical! Platform integration has significant issues.")
        
        logger.info("\nIntegration Recommendations:")
        logger.info("1. Monitor service response times and optimize slow endpoints")
        logger.info("2. Implement comprehensive error handling and logging")
        logger.info("3. Add rate limiting and advanced security features")
        logger.info("4. Create automated integration test suite")
        logger.info("5. Set up continuous monitoring and alerting")

async def main():
    """Main integration test execution"""
    async with IntegrationWorkflowTester() as tester:
        await tester.run_integration_tests()

if __name__ == "__main__":
    asyncio.run(main())
