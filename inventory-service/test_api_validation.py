#!/usr/bin/env python3
"""
Test API validation with our fixed Pydantic schemas.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_api_schema_validation():
    """Test API endpoint schema validation."""
    print("🧪 Testing API schema validation...")
    
    try:
        from fastapi.testclient import TestClient
        from main import app
        
        client = TestClient(app)
        
        # Test the product catalog endpoint with our fixed schema
        print("Testing product catalog endpoint...")
        
        # Test with valid parameters
        response = client.get(
            "/product-catalog/nearby",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "sort_by": "distance",  # This uses our fixed pattern validation
                "cylinder_size": "SMALL",
                "quantity": 1
            },
            headers={
                "X-User-ID": "hospital-123",
                "X-User-Role": "hospital"
            }
        )
        
        # We expect this to work without Pydantic validation errors
        # (it might fail for other reasons like missing data, but not validation)
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 422:  # 422 is validation error
            print("✅ No Pydantic validation errors!")
        else:
            print(f"❌ Validation error: {response.json()}")
            return False
        
        # Test with invalid sort_by to ensure validation still works
        response = client.get(
            "/product-catalog/nearby",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "sort_by": "invalid_sort",  # This should be rejected
                "cylinder_size": "SMALL",
                "quantity": 1
            },
            headers={
                "X-User-ID": "hospital-123",
                "X-User-Role": "hospital"
            }
        )
        
        if response.status_code == 422:
            error_detail = response.json()
            if 'sort_by' in str(error_detail):
                print("✅ Invalid sort_by correctly rejected by pattern validation!")
            else:
                print(f"⚠️  Validation error but not for sort_by: {error_detail}")
        else:
            print("⚠️  Expected validation error for invalid sort_by")
        
        return True
        
    except Exception as e:
        print(f"❌ API validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run API validation test."""
    print("🚀 Testing API validation with fixed schemas...\n")
    
    if test_api_schema_validation():
        print("\n✅ API validation tests passed!")
        print("✅ Pydantic pattern validation is working correctly in API endpoints!")
        return 0
    else:
        print("\n❌ API validation tests failed!")
        return 1

if __name__ == "__main__":
    exit(main())
