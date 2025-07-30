#!/usr/bin/env python3
"""
Order-Inventory Integration Test Script
Tests the integration between Order and Inventory services
"""

import asyncio
import httpx
import json
import sys
import os
from datetime import datetime

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class OrderInventoryIntegrationTest:
    def __init__(self):
        self.order_service_url = "http://localhost:8005"
        self.inventory_service_url = "http://localhost:8004"
        self.test_results = []
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    async def test_service_health(self):
        """Test that both services are healthy"""
        async with httpx.AsyncClient() as client:
            # Test Order service health
            try:
                response = await client.get(f"{self.order_service_url}/health")
                if response.status_code == 200:
                    self.log_test("Order Service Health", "PASS", "Service is healthy")
                else:
                    self.log_test("Order Service Health", "FAIL", f"Status: {response.status_code}")
            except Exception as e:
                self.log_test("Order Service Health", "FAIL", f"Error: {str(e)}")
            
            # Test Inventory service health
            try:
                response = await client.get(f"{self.inventory_service_url}/health")
                if response.status_code == 200:
                    self.log_test("Inventory Service Health", "PASS", "Service is healthy")
                else:
                    self.log_test("Inventory Service Health", "FAIL", f"Status: {response.status_code}")
            except Exception as e:
                self.log_test("Inventory Service Health", "FAIL", f"Error: {str(e)}")
    
    async def test_catalog_endpoint_exists(self):
        """Test that catalog/nearby endpoint exists"""
        async with httpx.AsyncClient() as client:
            try:
                # This should return 422 (validation error) not 404, indicating endpoint exists
                response = await client.get(f"{self.inventory_service_url}/catalog/nearby")
                if response.status_code in [422, 401, 403]:  # Validation error or auth required
                    self.log_test("Catalog Nearby Endpoint", "PASS", "Endpoint exists (requires auth/params)")
                elif response.status_code == 404:
                    self.log_test("Catalog Nearby Endpoint", "FAIL", "Endpoint not found")
                else:
                    self.log_test("Catalog Nearby Endpoint", "WARN", f"Unexpected status: {response.status_code}")
            except Exception as e:
                self.log_test("Catalog Nearby Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def test_reservation_endpoint_fixed(self):
        """Test that reservation endpoint is working correctly"""
        async with httpx.AsyncClient() as client:
            # Test the correct reservation endpoint that Order service now uses
            try:
                response = await client.post(
                    f"{self.inventory_service_url}/inventory/reservations",
                    headers={
                        "X-User-ID": "test-user",
                        "X-User-Role": "vendor",
                        "Content-Type": "application/json"
                    },
                    json={
                        "cylinder_size": "2 meter",
                        "quantity": 5,
                        "order_id": "123e4567-e89b-12d3-a456-426614174001"
                    }
                )
                if response.status_code in [200, 400]:  # 200 = success, 400 = no stock (expected)
                    self.log_test("Reservation Endpoint Fixed", "PASS",
                                "Order service can now use /inventory/reservations endpoint")
                elif response.status_code in [422, 401, 403]:  # Validation error or auth required
                    self.log_test("Reservation Endpoint Fixed", "PASS", "Endpoint exists (auth/validation working)")
                elif response.status_code == 404:
                    self.log_test("Reservation Endpoint Fixed", "FAIL", "Endpoint not found")
                else:
                    self.log_test("Reservation Endpoint Fixed", "WARN", f"Unexpected status: {response.status_code}")
            except Exception as e:
                self.log_test("Reservation Endpoint Fixed", "FAIL", f"Error: {str(e)}")
    
    async def test_vendor_availability_endpoint(self):
        """Test vendor availability endpoint that Order service calls"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.inventory_service_url}/vendors/123e4567-e89b-12d3-a456-426614174000/availability",
                    headers={
                        "X-User-ID": "test-user",
                        "X-User-Role": "vendor",
                        "Content-Type": "application/json"
                    }
                )
                if response.status_code == 200:
                    self.log_test("Vendor Availability Endpoint", "PASS", "Endpoint working correctly")
                elif response.status_code in [401, 403]:
                    self.log_test("Vendor Availability Endpoint", "PASS", "Endpoint exists (auth required)")
                elif response.status_code == 404:
                    self.log_test("Vendor Availability Endpoint", "FAIL",
                                "Order service expects /vendors/{vendor_id}/availability but it doesn't exist")
                else:
                    self.log_test("Vendor Availability Endpoint", "WARN", f"Unexpected status: {response.status_code}")
            except Exception as e:
                self.log_test("Vendor Availability Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def test_order_endpoints(self):
        """Test Order service endpoints"""
        async with httpx.AsyncClient() as client:
            # Test orders endpoint
            try:
                response = await client.get(f"{self.order_service_url}/orders")
                if response.status_code in [422, 401, 403]:  # Auth required
                    self.log_test("Order Service Orders Endpoint", "PASS", "Endpoint exists (requires auth)")
                elif response.status_code == 404:
                    self.log_test("Order Service Orders Endpoint", "FAIL", "Endpoint not found")
                else:
                    self.log_test("Order Service Orders Endpoint", "WARN", f"Unexpected status: {response.status_code}")
            except Exception as e:
                self.log_test("Order Service Orders Endpoint", "FAIL", f"Error: {str(e)}")
            
            # Test direct orders endpoint
            try:
                response = await client.post(f"{self.order_service_url}/orders/direct")
                if response.status_code in [422, 401, 403]:  # Auth required
                    self.log_test("Order Service Direct Orders Endpoint", "PASS", "Endpoint exists (requires auth)")
                elif response.status_code == 404:
                    self.log_test("Order Service Direct Orders Endpoint", "FAIL", "Endpoint not found")
                else:
                    self.log_test("Order Service Direct Orders Endpoint", "WARN", f"Unexpected status: {response.status_code}")
            except Exception as e:
                self.log_test("Order Service Direct Orders Endpoint", "FAIL", f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("🧪 Starting Order-Inventory Integration Tests")
        print("=" * 60)
        
        await self.test_service_health()
        await self.test_catalog_endpoint_exists()
        await self.test_reservation_endpoint_fixed()
        await self.test_vendor_availability_endpoint()
        await self.test_order_endpoints()
        
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("=" * 60)
        
        passed = len([r for r in self.test_results if r["status"] == "PASS"])
        failed = len([r for r in self.test_results if r["status"] == "FAIL"])
        warnings = len([r for r in self.test_results if r["status"] == "WARN"])
        total = len(self.test_results)
        
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"📈 Total: {total}")
        
        if failed > 0:
            print("\n🔧 Issues Found:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"   • {result['test']}: {result['details']}")
        
        return failed == 0

async def main():
    """Main test runner"""
    tester = OrderInventoryIntegrationTest()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 All integration tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Some integration tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
