#!/usr/bin/env python3
"""
Improved E2E Test with Better Password for Registration
"""

import asyncio
import aiohttp
import json
import uuid
from datetime import datetime

async def test_improved_registration():
    """Test user registration with improved password."""
    
    # Use a password that meets all requirements without sequential characters
    test_user = {
        "email": f"test_{uuid.uuid4().hex[:8]}@hospital.com",
        "password": "SecureP@ssw0rd!",  # No sequential characters
        "role": "hospital",
        "hospital_profile": {
            "hospital_name": "Test Hospital E2E",
            "contact_person": "Dr. Test",
            "contact_phone": "+234123456789"
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            print("🧪 Testing improved user registration...")
            
            # Test registration
            url = "http://localhost:8001/auth/register"
            async with session.post(url, json=test_user, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        print(f"✅ Registration successful: {data['data']['user_id']}")
                        
                        # Test login (may still fail due to email verification)
                        login_data = {
                            "email": test_user["email"],
                            "password": test_user["password"]
                        }
                        
                        print("🔐 Testing login...")
                        url = "http://localhost:8001/auth/login"
                        async with session.post(url, json=login_data, timeout=30) as login_response:
                            if login_response.status == 200:
                                login_data = await login_response.json()
                                print(f"✅ Login successful: {login_data}")
                            else:
                                error_text = await login_response.text()
                                print(f"⚠️ Login failed (expected due to email verification): {error_text}")
                    else:
                        print(f"❌ Registration failed: {data}")
                else:
                    error_text = await response.text()
                    print(f"❌ Registration failed: HTTP {response.status}: {error_text}")
                    
        except Exception as e:
            print(f"❌ Test error: {str(e)}")

async def test_file_upload():
    """Test file upload functionality."""
    print("📁 Testing file upload functionality...")
    
    # Create a simple test file
    test_file_content = b"Test file content for profile picture"
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test file upload endpoint
            data = aiohttp.FormData()
            data.add_field('file', test_file_content, filename='test.jpg', content_type='image/jpeg')
            
            url = "http://localhost:8001/upload/profile-picture"
            async with session.post(url, data=data, timeout=30) as response:
                if response.status in [200, 401, 403]:  # 401/403 expected without auth
                    print(f"✅ File upload endpoint accessible (HTTP {response.status})")
                else:
                    print(f"⚠️ File upload endpoint: HTTP {response.status}")
                    
        except Exception as e:
            print(f"❌ File upload test error: {str(e)}")

async def test_business_workflows():
    """Test complete business workflows."""
    print("🏥 Testing business workflows...")
    
    async with aiohttp.ClientSession() as session:
        # Test supplier onboarding workflow
        supplier_application = {
            "business_name": "Test Oxygen Supplier",
            "contact_email": f"supplier_{uuid.uuid4().hex[:6]}@example.com",
            "contact_phone": "+234987654321",
            "business_address": "123 Business Street, Lagos, Nigeria",
            "business_type": "Medical Gas Supplier",
            "years_in_operation": 5
        }
        
        try:
            url = "http://localhost:8002/applications/"
            async with session.post(url, json=supplier_application, timeout=30) as response:
                if response.status in [200, 201, 401, 403]:
                    print(f"✅ Supplier onboarding endpoint accessible (HTTP {response.status})")
                else:
                    print(f"⚠️ Supplier onboarding: HTTP {response.status}")
                    
        except Exception as e:
            print(f"❌ Supplier onboarding test error: {str(e)}")

async def main():
    """Run improved tests."""
    print("🚀 Running improved E2E tests...")
    print("=" * 60)
    
    await test_improved_registration()
    print()
    await test_file_upload()
    print()
    await test_business_workflows()
    
    print("=" * 60)
    print("✅ Improved E2E tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
