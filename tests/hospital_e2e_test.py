#!/usr/bin/env python3
"""
Comprehensive End-to-End Testing for Hospital User Journey
Flow-Backend Microservices Testing Suite
"""

import asyncio
import aiohttp
import json
import logging
import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('hospital_e2e_test.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Test result data structure"""
    test_name: str
    status: str  # PASS, FAIL, SKIP
    duration: float
    details: str
    error: Optional[str] = None
    response_data: Optional[Dict] = None

@dataclass
class HospitalUser:
    """Hospital user test data"""
    email: str
    password: str
    first_name: str
    last_name: str
    hospital_name: str
    registration_number: str
    license_number: str
    contact_person: str
    contact_phone: str
    emergency_contact: str
    bed_capacity: str
    hospital_type: str
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

class HospitalE2ETestSuite:
    """Comprehensive hospital user journey testing"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.test_results: List[TestResult] = []
        self.hospital_user = HospitalUser(
            email=f"test_hospital_{int(time.time())}@example.com",
            password="SecureHospitalPass123!",
            first_name="Dr. John",
            last_name="Smith",
            hospital_name="City General Hospital",
            registration_number="CGH-2024-001",
            license_number="MED-LIC-12345",
            contact_person="Dr. John Smith",
            contact_phone="+234-801-234-5678",
            emergency_contact="+234-801-234-5679",
            bed_capacity="200",
            hospital_type="public"
        )
        
    async def setup(self):
        """Setup test environment"""
        logger.info("🚀 Setting up Hospital E2E Test Suite")
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Verify services are running
        await self._verify_services()
        
    async def teardown(self):
        """Cleanup test environment"""
        logger.info("🧹 Cleaning up test environment")
        
        if self.session:
            await self.session.close()
            
    async def _verify_services(self):
        """Verify all required services are running"""
        logger.info("🔍 Verifying microservices availability...")

        # First check API Gateway
        max_retries = 30
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                async with self.session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        logger.info("✅ API Gateway is healthy")
                        break
                    else:
                        logger.warning(f"⚠️ API Gateway returned status {response.status}")
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Waiting for API Gateway... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ API Gateway is not accessible after {max_retries} attempts: {e}")
                    return

        # Check individual services through direct ports (for debugging)
        direct_services = [
            ("User Service", "http://localhost:8001/health"),
            ("Order Service", "http://localhost:8005/health"),
            ("Payment Service", "http://localhost:8008/health"),
            ("Location Service", "http://localhost:8003/health"),
            ("Notification Service", "http://localhost:8010/health"),
            ("Review Service", "http://localhost:8009/health"),
        ]

        for service_name, health_url in direct_services:
            try:
                async with self.session.get(health_url) as response:
                    if response.status == 200:
                        logger.info(f"✅ {service_name} is healthy")
                    else:
                        logger.warning(f"⚠️ {service_name} returned status {response.status}")
            except Exception as e:
                logger.warning(f"⚠️ {service_name} is not accessible: {e}")

        # Wait a bit more for services to be fully ready
        logger.info("⏳ Waiting for services to be fully ready...")
        await asyncio.sleep(10)
                
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        auth_required: bool = False
    ) -> Dict:
        """Make HTTP request with proper error handling"""
        
        url = f"{self.base_url}{endpoint}"
        request_headers = {"Content-Type": "application/json"}
        
        if headers:
            request_headers.update(headers)
            
        if auth_required and self.hospital_user.access_token:
            request_headers["Authorization"] = f"Bearer {self.hospital_user.access_token}"
            
        try:
            async with self.session.request(
                method, 
                url, 
                json=data, 
                headers=request_headers
            ) as response:
                response_text = await response.text()
                
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError:
                    response_data = {"raw_response": response_text}
                
                return {
                    "status_code": response.status,
                    "data": response_data,
                    "headers": dict(response.headers)
                }
                
        except Exception as e:
            return {
                "status_code": 0,
                "data": {"error": str(e)},
                "headers": {}
            }
    
    async def _record_test_result(
        self, 
        test_name: str, 
        start_time: float, 
        success: bool, 
        details: str,
        error: Optional[str] = None,
        response_data: Optional[Dict] = None
    ):
        """Record test result"""
        duration = time.time() - start_time
        status = "PASS" if success else "FAIL"
        
        result = TestResult(
            test_name=test_name,
            status=status,
            duration=duration,
            details=details,
            error=error,
            response_data=response_data
        )
        
        self.test_results.append(result)
        
        status_emoji = "✅" if success else "❌"
        logger.info(f"{status_emoji} {test_name}: {status} ({duration:.2f}s)")
        
        if error:
            logger.error(f"   Error: {error}")
            
    # Test Methods will be added in the next part
    async def test_hospital_registration(self):
        """Test hospital user registration"""
        test_name = "Hospital User Registration"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            registration_data = {
                "email": self.hospital_user.email,
                "password": self.hospital_user.password,
                "role": "hospital",
                "first_name": self.hospital_user.first_name,
                "last_name": self.hospital_user.last_name
            }
            
            response = await self._make_request("POST", "/auth/register", registration_data)
            
            if response["status_code"] == 200 and response["data"].get("success"):
                self.hospital_user.user_id = response["data"]["data"]["user_id"]
                await self._record_test_result(
                    test_name, start_time, True, 
                    f"Hospital user registered successfully with ID: {self.hospital_user.user_id}",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Registration failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Registration failed with exception",
                error=str(e)
            )
            return False
    
    async def test_hospital_login(self):
        """Test hospital user login"""
        test_name = "Hospital User Login"
        start_time = time.time()
        
        try:
            logger.info(f"🧪 Testing: {test_name}")
            
            login_data = {
                "email": self.hospital_user.email,
                "password": self.hospital_user.password
            }
            
            response = await self._make_request("POST", "/auth/login", login_data)
            
            if response["status_code"] == 200 and response["data"].get("success"):
                token_data = response["data"]["data"]
                self.hospital_user.access_token = token_data.get("access_token")
                self.hospital_user.refresh_token = token_data.get("refresh_token")
                
                await self._record_test_result(
                    test_name, start_time, True,
                    "Hospital user logged in successfully",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Login failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False
                
        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Login failed with exception",
                error=str(e)
            )
            return False

    async def test_hospital_profile_setup(self):
        """Test hospital profile creation and setup"""
        test_name = "Hospital Profile Setup"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            profile_data = {
                "hospital_name": self.hospital_user.hospital_name,
                "registration_number": self.hospital_user.registration_number,
                "license_number": self.hospital_user.license_number,
                "contact_person": self.hospital_user.contact_person,
                "contact_phone": self.hospital_user.contact_phone,
                "emergency_contact": self.hospital_user.emergency_contact,
                "bed_capacity": self.hospital_user.bed_capacity,
                "hospital_type": self.hospital_user.hospital_type,
                "services_offered": "Emergency Care, ICU, General Medicine, Surgery"
            }

            response = await self._make_request(
                "POST", "/users/profile/hospital",
                profile_data,
                auth_required=True
            )

            if response["status_code"] == 200:
                await self._record_test_result(
                    test_name, start_time, True,
                    "Hospital profile created successfully",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Profile setup failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Profile setup failed with exception",
                error=str(e)
            )
            return False

    async def test_delivery_location_management(self):
        """Test delivery location creation and management"""
        test_name = "Delivery Location Management"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            location_data = {
                "name": "Main Hospital Building",
                "address": "123 Hospital Street, Medical District, Lagos",
                "latitude": 6.5244,
                "longitude": 3.3792,
                "city": "Lagos",
                "state": "Lagos",
                "country": "Nigeria",
                "postal_code": "100001",
                "location_type": "hospital",
                "is_default": True,
                "delivery_instructions": "Deliver to main reception. Call emergency contact for after-hours delivery."
            }

            response = await self._make_request(
                "POST", "/locations",
                location_data,
                auth_required=True
            )

            if response["status_code"] == 200:
                await self._record_test_result(
                    test_name, start_time, True,
                    "Delivery location created successfully",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Location creation failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Location management failed with exception",
                error=str(e)
            )
            return False

    async def test_oxygen_order_creation(self):
        """Test oxygen cylinder order creation"""
        test_name = "Oxygen Order Creation"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            order_data = {
                "items": [
                    {
                        "cylinder_size": "D-Size",
                        "quantity": 10,
                        "urgency": "standard"
                    },
                    {
                        "cylinder_size": "E-Size",
                        "quantity": 5,
                        "urgency": "standard"
                    }
                ],
                "delivery_address": "123 Hospital Street, Medical District, Lagos",
                "delivery_latitude": 6.5244,
                "delivery_longitude": 3.3792,
                "required_delivery_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "delivery_instructions": "Deliver to main reception during business hours",
                "priority": "normal",
                "is_emergency": False,
                "notes": "Regular monthly oxygen supply order"
            }

            response = await self._make_request(
                "POST", "/orders",
                order_data,
                auth_required=True
            )

            if response["status_code"] == 200:
                order_id = response["data"]["data"]["order_id"]
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Order created successfully with ID: {order_id}",
                    response_data=response["data"]
                )
                return order_id
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Order creation failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return None

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Order creation failed with exception",
                error=str(e)
            )
            return None

    async def test_emergency_order_creation(self):
        """Test emergency oxygen order creation"""
        test_name = "Emergency Order Creation"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            emergency_order_data = {
                "items": [
                    {
                        "cylinder_size": "E-Size",
                        "quantity": 20,
                        "urgency": "emergency"
                    }
                ],
                "delivery_address": "123 Hospital Street, Medical District, Lagos",
                "delivery_latitude": 6.5244,
                "delivery_longitude": 3.3792,
                "required_delivery_date": datetime.now().isoformat(),
                "delivery_instructions": "EMERGENCY DELIVERY - Contact Dr. Smith immediately upon arrival",
                "priority": "emergency",
                "is_emergency": True,
                "notes": "Critical oxygen shortage in ICU - immediate delivery required"
            }

            response = await self._make_request(
                "POST", "/orders",
                emergency_order_data,
                auth_required=True
            )

            if response["status_code"] == 200:
                order_id = response["data"]["data"]["order_id"]
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Emergency order created successfully with ID: {order_id}",
                    response_data=response["data"]
                )
                return order_id
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Emergency order creation failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return None

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Emergency order creation failed with exception",
                error=str(e)
            )
            return None

    async def test_payment_initialization(self, order_id: str):
        """Test payment initialization for an order"""
        test_name = "Payment Initialization"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            payment_data = {
                "order_id": order_id,
                "amount": 150000.00,  # 1,500 NGN
                "currency": "NGN",
                "payment_method": "card"
            }

            response = await self._make_request(
                "POST", "/payments/initialize",
                payment_data,
                auth_required=True
            )

            if response["status_code"] == 200:
                payment_data = response["data"]["data"]
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Payment initialized successfully with reference: {payment_data.get('reference')}",
                    response_data=response["data"]
                )
                return payment_data.get("reference")
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Payment initialization failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return None

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Payment initialization failed with exception",
                error=str(e)
            )
            return None

    async def test_order_tracking(self, order_id: str):
        """Test order tracking and status updates"""
        test_name = "Order Tracking"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            response = await self._make_request(
                "GET", f"/orders/{order_id}",
                auth_required=True
            )

            if response["status_code"] == 200:
                order_data = response["data"]["data"]
                await self._record_test_result(
                    test_name, start_time, True,
                    f"Order tracking successful - Status: {order_data.get('status')}",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Order tracking failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Order tracking failed with exception",
                error=str(e)
            )
            return False

    async def test_jwt_token_refresh(self):
        """Test JWT token refresh mechanism"""
        test_name = "JWT Token Refresh"
        start_time = time.time()

        try:
            logger.info(f"🧪 Testing: {test_name}")

            if not self.hospital_user.refresh_token:
                await self._record_test_result(
                    test_name, start_time, False,
                    "No refresh token available for testing",
                    error="Missing refresh token"
                )
                return False

            refresh_data = {
                "refresh_token": self.hospital_user.refresh_token
            }

            response = await self._make_request(
                "POST", "/auth/refresh",
                refresh_data
            )

            if response["status_code"] == 200:
                token_data = response["data"]["data"]
                self.hospital_user.access_token = token_data.get("access_token")

                await self._record_test_result(
                    test_name, start_time, True,
                    "Token refresh successful",
                    response_data=response["data"]
                )
                return True
            else:
                await self._record_test_result(
                    test_name, start_time, False,
                    f"Token refresh failed with status {response['status_code']}",
                    error=str(response["data"]),
                    response_data=response["data"]
                )
                return False

        except Exception as e:
            await self._record_test_result(
                test_name, start_time, False,
                "Token refresh failed with exception",
                error=str(e)
            )
            return False

    async def run_all_tests(self):
        """Run all hospital user journey tests"""
        logger.info("🚀 Starting Hospital User Journey E2E Tests")

        # Test sequence following hospital user workflow
        test_sequence = [
            ("Hospital Registration", self.test_hospital_registration),
            ("Hospital Login", self.test_hospital_login),
            ("Hospital Profile Setup", self.test_hospital_profile_setup),
            ("Delivery Location Management", self.test_delivery_location_management),
            ("JWT Token Refresh", self.test_jwt_token_refresh),
        ]

        # Run basic tests first
        for test_name, test_func in test_sequence:
            success = await test_func()
            if not success and test_name in ["Hospital Registration", "Hospital Login"]:
                logger.error(f"❌ Critical test failed: {test_name}. Stopping test suite.")
                return False

        # Test order creation and payment flow
        order_id = await self.test_oxygen_order_creation()
        if order_id:
            await self.test_payment_initialization(order_id)
            await self.test_order_tracking(order_id)

        # Test emergency order flow
        emergency_order_id = await self.test_emergency_order_creation()
        if emergency_order_id:
            await self.test_order_tracking(emergency_order_id)

        return True

    def generate_test_report(self) -> str:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r.status == "PASS"])
        failed_tests = len([r for r in self.test_results if r.status == "FAIL"])

        report = f"""
# Hospital User Journey E2E Test Report
Generated: {datetime.now().isoformat()}

## Summary
- **Total Tests**: {total_tests}
- **Passed**: {passed_tests} ✅
- **Failed**: {failed_tests} ❌
- **Success Rate**: {(passed_tests/total_tests*100):.1f}%

## Test Results
"""

        for result in self.test_results:
            status_emoji = "✅" if result.status == "PASS" else "❌"
            report += f"\n### {status_emoji} {result.test_name}\n"
            report += f"- **Status**: {result.status}\n"
            report += f"- **Duration**: {result.duration:.2f}s\n"
            report += f"- **Details**: {result.details}\n"

            if result.error:
                report += f"- **Error**: {result.error}\n"

            if result.response_data:
                report += f"- **Response**: {json.dumps(result.response_data, indent=2)}\n"

            report += "\n"

        return report

# Main execution function
async def main():
    """Main test execution"""
    test_suite = HospitalE2ETestSuite()

    try:
        await test_suite.setup()
        success = await test_suite.run_all_tests()

        # Generate and save report
        report = test_suite.generate_test_report()

        with open("hospital_e2e_test_report.md", "w") as f:
            f.write(report)

        logger.info("📊 Test report saved to hospital_e2e_test_report.md")

        # Print summary
        total_tests = len(test_suite.test_results)
        passed_tests = len([r for r in test_suite.test_results if r.status == "PASS"])

        if passed_tests == total_tests:
            logger.info(f"🎉 All {total_tests} tests passed!")
            return 0
        else:
            logger.error(f"❌ {total_tests - passed_tests} out of {total_tests} tests failed")
            return 1

    except Exception as e:
        logger.error(f"❌ Test suite failed with exception: {e}")
        return 1
    finally:
        await test_suite.teardown()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
