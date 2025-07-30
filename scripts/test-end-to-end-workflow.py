#!/usr/bin/env python3
"""
End-to-End Workflow Testing Script
Tests complete hospital ordering workflows for the Flow-Backend platform
"""

import asyncio
import httpx
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any

class EndToEndWorkflowTest:
    def __init__(self):
        self.order_service_url = "http://localhost:8005"
        self.inventory_service_url = "http://localhost:8004"
        self.test_results = []
        
        # Mock authentication headers for testing
        self.hospital_headers = {
            "X-User-ID": "test-hospital-123",
            "X-User-Role": "HOSPITAL",
            "Content-Type": "application/json"
        }
        
        self.vendor_headers = {
            "X-User-ID": "test-vendor-456",
            "X-User-Role": "VENDOR",
            "Content-Type": "application/json"
        }
    
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
    
    async def test_browse_inventory_catalog(self):
        """Test Step 1: Hospital browses available inventory"""
        async with httpx.AsyncClient() as client:
            try:
                # Test catalog browsing with mock hospital location
                response = await client.get(
                    f"{self.inventory_service_url}/catalog/nearby",
                    params={
                        "latitude": 6.5244,  # Lagos coordinates
                        "longitude": 3.3792,
                        "cylinder_size": "SMALL",
                        "quantity": 5,
                        "max_distance_km": 50.0,
                        "is_emergency": False,
                        "sort_by": "distance"
                    },
                    headers=self.hospital_headers
                )
                
                if response.status_code == 200:
                    catalog_data = response.json()
                    self.log_test("Browse Inventory Catalog", "PASS", 
                                f"Retrieved catalog with {catalog_data.get('total', 0)} items")
                    return catalog_data
                elif response.status_code == 403:
                    self.log_test("Browse Inventory Catalog", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                else:
                    self.log_test("Browse Inventory Catalog", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Browse Inventory Catalog", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_check_inventory_availability(self):
        """Test Step 2: Check specific inventory availability"""
        async with httpx.AsyncClient() as client:
            try:
                availability_check = {
                    "vendor_id": "test-vendor-456",
                    "location_id": "test-location-789",
                    "cylinder_size": "SMALL",
                    "quantity": 5
                }
                
                response = await client.post(
                    f"{self.inventory_service_url}/catalog/availability/check",
                    json=availability_check,
                    headers=self.hospital_headers
                )
                
                if response.status_code == 200:
                    availability_data = response.json()
                    self.log_test("Check Inventory Availability", "PASS", 
                                f"Availability check completed: {availability_data.get('is_available', False)}")
                    return availability_data
                elif response.status_code == 403:
                    self.log_test("Check Inventory Availability", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                else:
                    self.log_test("Check Inventory Availability", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Check Inventory Availability", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_place_direct_order(self):
        """Test Step 3: Hospital places a direct order"""
        async with httpx.AsyncClient() as client:
            try:
                order_data = {
                    "items": [
                        {
                            "cylinder_size": "SMALL",
                            "quantity": 5,
                            "unit_price": 150.0
                        }
                    ],
                    "delivery_address": "123 Hospital Street, Lagos, Nigeria",
                    "delivery_latitude": 6.5244,
                    "delivery_longitude": 3.3792,
                    "delivery_contact_name": "Dr. Smith",
                    "delivery_contact_phone": "+234-123-456-7890",
                    "is_emergency": False,
                    "notes": "Regular oxygen supply order",
                    "max_distance_km": 50.0,
                    "vendor_selection_criteria": "best_price"
                }
                
                response = await client.post(
                    f"{self.order_service_url}/orders/direct",
                    json=order_data,
                    headers=self.hospital_headers
                )
                
                if response.status_code == 200:
                    order_response = response.json()
                    self.log_test("Place Direct Order", "PASS", 
                                f"Order placed successfully: {order_response.get('order_id', 'N/A')}")
                    return order_response
                elif response.status_code == 403:
                    self.log_test("Place Direct Order", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                elif response.status_code == 422:
                    error_details = response.json()
                    self.log_test("Place Direct Order", "FAIL", 
                                f"Validation error: {error_details}")
                    return None
                else:
                    self.log_test("Place Direct Order", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Place Direct Order", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_order_pricing_calculation(self):
        """Test Step 4: Calculate order pricing"""
        async with httpx.AsyncClient() as client:
            try:
                pricing_request = {
                    "items": [
                        {
                            "cylinder_size": "SMALL",
                            "quantity": 5
                        }
                    ],
                    "delivery_latitude": 6.5244,
                    "delivery_longitude": 3.3792,
                    "is_emergency": False,
                    "max_distance_km": 50.0
                }
                
                response = await client.post(
                    f"{self.order_service_url}/orders/pricing",
                    json=pricing_request,
                    headers=self.hospital_headers
                )
                
                if response.status_code == 200:
                    pricing_data = response.json()
                    self.log_test("Order Pricing Calculation", "PASS", 
                                f"Pricing calculated for {len(pricing_data.get('vendor_options', []))} vendors")
                    return pricing_data
                elif response.status_code == 403:
                    self.log_test("Order Pricing Calculation", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                else:
                    self.log_test("Order Pricing Calculation", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Order Pricing Calculation", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_inventory_reservation_workflow(self):
        """Test Step 5: Test inventory reservation (will likely fail due to endpoint mismatch)"""
        async with httpx.AsyncClient() as client:
            try:
                # Test the correct reservation endpoint
                reservation_data = {
                    "inventory_id": "test-inventory-123",
                    "cylinder_size": "SMALL",
                    "quantity": 5,
                    "order_id": "test-order-456",
                    "expires_at": "2025-07-30T21:00:00Z"
                }
                
                response = await client.post(
                    f"{self.inventory_service_url}/inventory/reservations",
                    json=reservation_data,
                    headers=self.vendor_headers
                )
                
                if response.status_code == 200:
                    reservation_response = response.json()
                    self.log_test("Inventory Reservation", "PASS", 
                                f"Reservation created: {reservation_response.get('reservation_id', 'N/A')}")
                    return reservation_response
                elif response.status_code == 403:
                    self.log_test("Inventory Reservation", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                elif response.status_code == 422:
                    error_details = response.json()
                    self.log_test("Inventory Reservation", "FAIL", 
                                f"Validation error: {error_details}")
                    return None
                else:
                    self.log_test("Inventory Reservation", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Inventory Reservation", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_order_status_tracking(self):
        """Test Step 6: Track order status"""
        async with httpx.AsyncClient() as client:
            try:
                # Test getting orders list
                response = await client.get(
                    f"{self.order_service_url}/orders",
                    params={"page": 1, "size": 10},
                    headers=self.hospital_headers
                )
                
                if response.status_code == 200:
                    orders_data = response.json()
                    self.log_test("Order Status Tracking", "PASS", 
                                f"Retrieved {orders_data.get('total', 0)} orders")
                    return orders_data
                elif response.status_code == 403:
                    self.log_test("Order Status Tracking", "FAIL", 
                                "Authentication failed - service requires proper auth")
                    return None
                else:
                    self.log_test("Order Status Tracking", "FAIL", 
                                f"Unexpected status: {response.status_code}")
                    return None
            except Exception as e:
                self.log_test("Order Status Tracking", "FAIL", f"Error: {str(e)}")
                return None
    
    async def test_integration_issues_simulation(self):
        """Test Step 7: Simulate the integration issues we found"""
        async with httpx.AsyncClient() as client:
            # Test the endpoint mismatch that Order service would encounter
            try:
                response = await client.post(
                    f"{self.inventory_service_url}/inventory/test-location/reserve",
                    json={"cylinder_size": "SMALL", "quantity": 5, "order_id": "test-order"}
                )
                
                if response.status_code == 404:
                    self.log_test("Integration Issue - Reservation Endpoint", "FAIL", 
                                "Order service would fail: /inventory/{location_id}/reserve endpoint doesn't exist")
                else:
                    self.log_test("Integration Issue - Reservation Endpoint", "PASS", 
                                "Endpoint exists (unexpected)")
            except Exception as e:
                self.log_test("Integration Issue - Reservation Endpoint", "FAIL", f"Error: {str(e)}")
            
            # Test vendor availability endpoint
            try:
                response = await client.get(
                    f"{self.inventory_service_url}/vendors/test-vendor/availability"
                )
                
                if response.status_code == 404:
                    self.log_test("Integration Issue - Vendor Availability", "FAIL", 
                                "Order service would fail: /vendors/{vendor_id}/availability endpoint doesn't exist")
                else:
                    self.log_test("Integration Issue - Vendor Availability", "PASS", 
                                "Endpoint exists (unexpected)")
            except Exception as e:
                self.log_test("Integration Issue - Vendor Availability", "FAIL", f"Error: {str(e)}")
    
    async def run_all_tests(self):
        """Run all end-to-end workflow tests"""
        print("🏥 Starting End-to-End Hospital Workflow Tests")
        print("=" * 60)
        
        # Run workflow tests in order
        catalog_data = await self.test_browse_inventory_catalog()
        availability_data = await self.test_check_inventory_availability()
        pricing_data = await self.test_order_pricing_calculation()
        order_data = await self.test_place_direct_order()
        reservation_data = await self.test_inventory_reservation_workflow()
        tracking_data = await self.test_order_status_tracking()
        
        # Test integration issues
        await self.test_integration_issues_simulation()
        
        print("\n" + "=" * 60)
        print("📊 Workflow Test Summary")
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
    tester = EndToEndWorkflowTest()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 All end-to-end workflow tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Some end-to-end workflow tests failed!")
        print("\nNote: Some failures are expected due to authentication requirements")
        print("and integration issues identified in previous tests.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
