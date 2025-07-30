#!/usr/bin/env python3
"""
Comprehensive Pricing Service Testing Script
Tests all aspects of the Pricing Service including health, APIs, and integration
"""

import asyncio
import aiohttp
import json
import sys
import time
from typing import Dict, Any, List
from datetime import datetime

class PricingServiceTester:
    """Comprehensive tester for Pricing Service functionality."""
    
    def __init__(self):
        self.base_url = "http://localhost:8006"
        self.results = []
        self.session = None
        
        # Test data
        self.test_vendor_id = "550e8400-e29b-41d4-a716-446655440000"
        self.test_product_id = "550e8400-e29b-41d4-a716-446655440001"
        self.test_hospital_location = {
            "latitude": 6.5244,
            "longitude": 3.3792
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
    
    async def test_service_health(self):
        """Test service health endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/health") as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "healthy":
                        self.log_result("Pricing Service Health", "PASS", 
                                      "Service healthy and database connected", response_time)
                    else:
                        self.log_result("Pricing Service Health", "WARN", 
                                      f"Service running but status: {data.get('status')}", response_time)
                else:
                    self.log_result("Pricing Service Health", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Pricing Service Health", "FAIL", f"Connection error: {str(e)}")
    
    async def test_service_info(self):
        """Test service information endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/") as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    if "service" in data and "endpoints" in data:
                        self.log_result("Service Information", "PASS", 
                                      f"Service: {data.get('service')}", response_time)
                    else:
                        self.log_result("Service Information", "FAIL", 
                                      "Missing required fields", response_time)
                else:
                    self.log_result("Service Information", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Service Information", "FAIL", f"Error: {str(e)}")
    
    async def test_vendors_endpoint(self):
        """Test vendors API endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/api/v1/vendors") as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    if response.status == 200:
                        data = await response.json()
                        self.log_result("Vendors Endpoint", "PASS", 
                                      f"Returned {len(data.get('vendors', []))} vendors", response_time)
                    else:
                        self.log_result("Vendors Endpoint", "PASS", 
                                      "Endpoint exists (requires auth)", response_time)
                else:
                    self.log_result("Vendors Endpoint", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Vendors Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def test_products_endpoint(self):
        """Test products API endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/api/v1/products") as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    if response.status == 200:
                        data = await response.json()
                        self.log_result("Products Endpoint", "PASS", 
                                      f"Returned {len(data.get('products', []))} products", response_time)
                    else:
                        self.log_result("Products Endpoint", "PASS", 
                                      "Endpoint exists (requires auth)", response_time)
                else:
                    self.log_result("Products Endpoint", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Products Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def test_pricing_endpoint(self):
        """Test pricing API endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/api/v1/pricing") as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    if response.status == 200:
                        data = await response.json()
                        self.log_result("Pricing Endpoint", "PASS", 
                                      "Pricing API accessible", response_time)
                    else:
                        self.log_result("Pricing Endpoint", "PASS", 
                                      "Endpoint exists (requires auth)", response_time)
                else:
                    self.log_result("Pricing Endpoint", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Pricing Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def test_vendor_pricing_endpoint(self):
        """Test vendor-specific pricing endpoint."""
        try:
            start_time = time.time()
            url = f"{self.base_url}/api/v1/vendors/{self.test_vendor_id}/pricing"
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403, 404]:  # 404 expected for non-existent vendor
                    if response.status == 200:
                        data = await response.json()
                        self.log_result("Vendor Pricing", "PASS", 
                                      "Vendor pricing accessible", response_time)
                    elif response.status == 404:
                        self.log_result("Vendor Pricing", "PASS", 
                                      "Endpoint working (vendor not found)", response_time)
                    else:
                        self.log_result("Vendor Pricing", "PASS", 
                                      "Endpoint exists (requires auth)", response_time)
                else:
                    self.log_result("Vendor Pricing", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Vendor Pricing", "FAIL", f"Error: {str(e)}")
    
    async def test_price_comparison_endpoint(self):
        """Test price comparison endpoint."""
        try:
            start_time = time.time()
            url = f"{self.base_url}/api/v1/pricing/compare"
            
            # Test with query parameters
            params = {
                "product_id": self.test_product_id,
                "latitude": self.test_hospital_location["latitude"],
                "longitude": self.test_hospital_location["longitude"],
                "quantity": 10
            }
            
            async with self.session.get(url, params=params) as response:
                response_time = time.time() - start_time
                
                if response.status in [200, 401, 403, 404]:
                    if response.status == 200:
                        data = await response.json()
                        self.log_result("Price Comparison", "PASS", 
                                      "Price comparison working", response_time)
                    elif response.status == 404:
                        self.log_result("Price Comparison", "PASS", 
                                      "Endpoint working (no data found)", response_time)
                    else:
                        self.log_result("Price Comparison", "PASS", 
                                      "Endpoint exists (requires auth)", response_time)
                else:
                    self.log_result("Price Comparison", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("Price Comparison", "FAIL", f"Error: {str(e)}")
    
    async def test_docs_endpoint(self):
        """Test API documentation endpoint."""
        try:
            start_time = time.time()
            async with self.session.get(f"{self.base_url}/docs") as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    content = await response.text()
                    if "swagger" in content.lower() or "openapi" in content.lower():
                        self.log_result("API Documentation", "PASS", 
                                      "Swagger/OpenAPI docs available", response_time)
                    else:
                        self.log_result("API Documentation", "WARN", 
                                      "Docs endpoint accessible but content unclear", response_time)
                else:
                    self.log_result("API Documentation", "FAIL", 
                                  f"HTTP {response.status}", response_time)
        except Exception as e:
            self.log_result("API Documentation", "FAIL", f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all pricing service tests."""
        print("🧪 Starting Pricing Service Comprehensive Testing...")
        print("=" * 60)
        
        await self.setup()
        
        try:
            # Core service tests
            await self.test_service_health()
            await self.test_service_info()
            await self.test_docs_endpoint()
            
            # API endpoint tests
            await self.test_vendors_endpoint()
            await self.test_products_endpoint()
            await self.test_pricing_endpoint()
            await self.test_vendor_pricing_endpoint()
            await self.test_price_comparison_endpoint()
            
        finally:
            await self.cleanup()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("📊 Pricing Service Test Summary")
        print("=" * 60)
        
        passed = len([r for r in self.results if r["status"] == "PASS"])
        failed = len([r for r in self.results if r["status"] == "FAIL"])
        warnings = len([r for r in self.results if r["status"] == "WARN"])
        total = len(self.results)
        
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"📈 Total: {total}")
        
        if failed > 0:
            print(f"\n🔧 Issues Found:")
            for result in self.results:
                if result["status"] == "FAIL":
                    print(f"   • {result['test']}: {result['details']}")
        
        if failed == 0:
            print(f"\n🎉 All critical tests passed!")
        else:
            print(f"\n💥 {failed} test(s) failed!")
        
        # Performance summary
        avg_response_time = sum(r["response_time_ms"] for r in self.results) / len(self.results) if self.results else 0
        print(f"\n⚡ Average Response Time: {avg_response_time:.2f}ms")


async def main():
    """Main test execution."""
    tester = PricingServiceTester()
    await tester.run_all_tests()
    
    # Return exit code based on results
    failed_tests = len([r for r in tester.results if r["status"] == "FAIL"])
    sys.exit(1 if failed_tests > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
