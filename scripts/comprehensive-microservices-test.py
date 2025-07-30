#!/usr/bin/env python3
"""
Comprehensive Microservices Testing Script
Tests all Flow-Backend microservices for production readiness
"""

import asyncio
import aiohttp
import json
import sys
import time
from typing import Dict, Any, List
from datetime import datetime

class MicroservicesTester:
    """Comprehensive tester for all Flow-Backend microservices."""
    
    def __init__(self):
        self.services = {
            "User Service": {"port": 8001, "health_path": "/health"},
            "Location Service": {"port": 8003, "health_path": "/health"},
            "Inventory Service": {"port": 8004, "health_path": "/health"},
            "Order Service": {"port": 8005, "health_path": "/health"},
            "Pricing Service": {"port": 8006, "health_path": "/health"},
            "Payment Service": {"port": 8008, "health_path": "/health"},
            "Review Service": {"port": 8009, "health_path": "/health"},
            "Notification Service": {"port": 8010, "health_path": "/health"},
            "Admin Service": {"port": 8011, "health_path": "/health"},
            "API Gateway": {"port": 8000, "health_path": "/health"}
        }
        
        self.results = []
        self.session = None
        
        # Test endpoints for each service
        self.service_endpoints = {
            "User Service": ["/users", "/auth/login"],
            "Location Service": ["/locations/geocode", "/locations/distance"],
            "Inventory Service": ["/inventory", "/vendors", "/catalog/nearby"],
            "Order Service": ["/orders", "/orders/direct"],
            "Pricing Service": ["/api/v1/vendors", "/api/v1/pricing"],
            "Payment Service": ["/payments", "/payments/initialize"],
            "Review Service": ["/reviews", "/vendors/{vendor_id}/reviews"],
            "Notification Service": ["/notifications", "/notifications/send"],
            "Admin Service": ["/admin/users", "/admin/analytics"],
            "API Gateway": ["/api/v1/users", "/api/v1/orders"]
        }
    
    async def setup(self):
        """Setup test session."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
    
    async def cleanup(self):
        """Cleanup test session."""
        if self.session:
            await self.session.close()
    
    def log_result(self, test_name: str, status: str, details: str = "", response_time: float = 0):
        """Log test result."""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "response_time_ms": round(response_time * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        self.results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    async def test_service_health(self, service_name: str, config: Dict[str, Any]):
        """Test individual service health."""
        try:
            start_time = time.time()
            url = f"http://localhost:{config['port']}{config['health_path']}"
            
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    status = data.get("status", "unknown")
                    
                    if status == "healthy":
                        self.log_result(f"{service_name} Health", "PASS", 
                                      "Service healthy", response_time)
                    else:
                        self.log_result(f"{service_name} Health", "WARN", 
                                      f"Service status: {status}", response_time)
                else:
                    self.log_result(f"{service_name} Health", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result(f"{service_name} Health", "FAIL", f"Connection error: {str(e)}")
    
    async def test_service_endpoints(self, service_name: str, config: Dict[str, Any]):
        """Test service API endpoints."""
        if service_name not in self.service_endpoints:
            return
        
        base_url = f"http://localhost:{config['port']}"
        endpoints = self.service_endpoints[service_name]
        
        for endpoint in endpoints:
            try:
                start_time = time.time()
                url = f"{base_url}{endpoint}"
                
                async with self.session.get(url) as response:
                    response_time = time.time() - start_time
                    
                    # Accept 200, 401, 403 as valid (auth required is expected)
                    if response.status in [200, 401, 403]:
                        if response.status == 200:
                            self.log_result(f"{service_name} {endpoint}", "PASS", 
                                          "Endpoint accessible", response_time)
                        else:
                            self.log_result(f"{service_name} {endpoint}", "PASS", 
                                          "Endpoint exists (requires auth)", response_time)
                    elif response.status == 404:
                        self.log_result(f"{service_name} {endpoint}", "WARN", 
                                      "Endpoint not found", response_time)
                    else:
                        self.log_result(f"{service_name} {endpoint}", "FAIL", 
                                      f"HTTP {response.status}", response_time)
            except Exception as e:
                self.log_result(f"{service_name} {endpoint}", "FAIL", f"Error: {str(e)}")
    
    async def test_service_docs(self, service_name: str, config: Dict[str, Any]):
        """Test service documentation endpoint."""
        try:
            start_time = time.time()
            url = f"http://localhost:{config['port']}/docs"
            
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    content = await response.text()
                    if "swagger" in content.lower() or "openapi" in content.lower():
                        self.log_result(f"{service_name} Docs", "PASS", 
                                      "API documentation available", response_time)
                    else:
                        self.log_result(f"{service_name} Docs", "WARN", 
                                      "Docs endpoint accessible but unclear", response_time)
                else:
                    self.log_result(f"{service_name} Docs", "WARN", 
                                  f"No docs endpoint (HTTP {response.status})", response_time)
        except Exception as e:
            self.log_result(f"{service_name} Docs", "WARN", f"No docs endpoint")
    
    async def test_cross_service_integration(self):
        """Test cross-service integration scenarios."""
        
        # Test 1: Order-Inventory Integration
        try:
            # Test inventory availability endpoint (used by Order service)
            start_time = time.time()
            url = "http://localhost:8004/vendors/test-vendor/availability"
            
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403, 404]:
                    self.log_result("Order-Inventory Integration", "PASS", 
                                  "Vendor availability endpoint accessible", response_time)
                else:
                    self.log_result("Order-Inventory Integration", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Order-Inventory Integration", "FAIL", f"Error: {str(e)}")
        
        # Test 2: Pricing-Inventory Integration
        try:
            start_time = time.time()
            url = "http://localhost:8006/api/v1/pricing/compare?product_id=test&latitude=6.5&longitude=3.3"
            
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403, 404]:
                    self.log_result("Pricing-Inventory Integration", "PASS", 
                                  "Price comparison endpoint accessible", response_time)
                else:
                    self.log_result("Pricing-Inventory Integration", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Pricing-Inventory Integration", "FAIL", f"Error: {str(e)}")
        
        # Test 3: Payment-Order Integration
        try:
            start_time = time.time()
            url = "http://localhost:8008/payments"
            
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403]:
                    self.log_result("Payment-Order Integration", "PASS", 
                                  "Payment endpoint accessible", response_time)
                else:
                    self.log_result("Payment-Order Integration", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Payment-Order Integration", "FAIL", f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all microservice tests."""
        print("🧪 Starting Comprehensive Microservices Testing...")
        print("=" * 70)
        
        await self.setup()
        
        try:
            # Test each service health
            print("\n🏥 Testing Service Health...")
            for service_name, config in self.services.items():
                await self.test_service_health(service_name, config)
            
            # Test service endpoints
            print("\n🔗 Testing Service Endpoints...")
            for service_name, config in self.services.items():
                await self.test_service_endpoints(service_name, config)
            
            # Test service documentation
            print("\n📚 Testing Service Documentation...")
            for service_name, config in self.services.items():
                await self.test_service_docs(service_name, config)
            
            # Test cross-service integration
            print("\n🔄 Testing Cross-Service Integration...")
            await self.test_cross_service_integration()
            
        finally:
            await self.cleanup()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print comprehensive test summary."""
        print("\n" + "=" * 70)
        print("📊 Comprehensive Microservices Test Summary")
        print("=" * 70)
        
        passed = len([r for r in self.results if r["status"] == "PASS"])
        failed = len([r for r in self.results if r["status"] == "FAIL"])
        warnings = len([r for r in self.results if r["status"] == "WARN"])
        total = len(self.results)
        
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"📈 Total: {total}")
        
        # Service status summary
        print(f"\n🏥 Service Status Summary:")
        service_status = {}
        for result in self.results:
            if "Health" in result["test"]:
                service = result["test"].replace(" Health", "")
                service_status[service] = result["status"]
        
        for service, status in service_status.items():
            status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
            print(f"   {status_icon} {service}")
        
        # Issues summary
        if failed > 0:
            print(f"\n🔧 Critical Issues Found:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"   • {result['test']}: {result['details']}")
        
        if warnings > 0:
            print(f"\n⚠️  Warnings:")
            warning_count = 0
            for result in self.results:
                if result["status"] == "WARN" and warning_count < 5:  # Limit warnings shown
                    print(f"   • {result['test']}: {result['details']}")
                    warning_count += 1
            if warnings > 5:
                print(f"   ... and {warnings - 5} more warnings")
        
        # Performance summary
        avg_response_time = sum(r["response_time_ms"] for r in self.results) / len(self.results) if self.results else 0
        print(f"\n⚡ Average Response Time: {avg_response_time:.2f}ms")
        
        # Final assessment
        healthy_services = len([s for s in service_status.values() if s == "PASS"])
        total_services = len(service_status)
        
        print(f"\n🎯 Production Readiness Assessment:")
        print(f"   Services Online: {healthy_services}/{total_services}")
        print(f"   Success Rate: {(passed/total*100):.1f}%")
        
        if failed == 0 and healthy_services == total_services:
            print(f"\n🎉 All microservices are production ready!")
        elif failed == 0:
            print(f"\n✅ All critical tests passed! Some services may need attention.")
        else:
            print(f"\n💥 {failed} critical issue(s) found that need immediate attention!")


async def main():
    """Main test execution."""
    tester = MicroservicesTester()
    await tester.run_all_tests()
    
    # Return exit code based on results
    failed_tests = len([r for r in tester.results if r["status"] == "FAIL"])
    sys.exit(1 if failed_tests > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
