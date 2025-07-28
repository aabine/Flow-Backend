#!/usr/bin/env python3
"""
Test script to verify our recent fixes:
1. Pydantic validation with pattern parameter
2. Authentication imports
3. SQLAlchemy Enum configurations
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_pydantic_validation():
    """Test Pydantic schemas with pattern parameter."""
    print("🧪 Testing Pydantic validation fixes...")
    
    try:
        from app.schemas.inventory import ProductCatalogRequest
        from pydantic import ValidationError
        
        # Test valid values
        request = ProductCatalogRequest(
            hospital_latitude=6.5244,
            hospital_longitude=3.3792,
            sort_by='distance',
            sort_order='asc'
        )
        print("✅ Valid ProductCatalogRequest created successfully")
        
        # Test invalid sort_by
        try:
            invalid_request = ProductCatalogRequest(
                hospital_latitude=6.5244,
                hospital_longitude=3.3792,
                sort_by='invalid_option',
                sort_order='asc'
            )
            print("❌ Should have failed for invalid sort_by")
            return False
        except ValidationError:
            print("✅ Correctly rejected invalid sort_by")
        
        # Test invalid sort_order
        try:
            invalid_request = ProductCatalogRequest(
                hospital_latitude=6.5244,
                hospital_longitude=3.3792,
                sort_by='distance',
                sort_order='invalid_order'
            )
            print("❌ Should have failed for invalid sort_order")
            return False
        except ValidationError:
            print("✅ Correctly rejected invalid sort_order")
            
        print("✅ Pydantic validation tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Pydantic validation test failed: {e}")
        return False

def test_authentication_imports():
    """Test authentication imports in API modules."""
    print("\n🧪 Testing authentication import fixes...")
    
    modules_to_test = [
        'app.api.product_catalog',
        'app.api.inventory', 
        'app.api.cylinders',
        'app.api.stock_movements'
    ]
    
    success_count = 0
    for module in modules_to_test:
        try:
            __import__(module)
            print(f"✅ {module} imports successfully!")
            success_count += 1
        except Exception as e:
            print(f"❌ {module} failed: {e}")
    
    if success_count == len(modules_to_test):
        print("✅ All authentication imports working!")
        return True
    else:
        print(f"❌ {len(modules_to_test) - success_count} modules failed to import")
        return False

def test_sqlalchemy_enum_models():
    """Test SQLAlchemy models with Enum columns."""
    print("\n🧪 Testing SQLAlchemy Enum fixes...")
    
    try:
        # Test importing models with Enum columns
        from app.models.cylinder import (
            Cylinder, CylinderLifecycleState, CylinderCondition, 
            MaintenanceType, QualityCheckStatus
        )
        from app.models.inventory import CylinderStock, StockMovement, StockReservation
        from shared.models import CylinderSize
        
        print("✅ All models with Enum columns imported successfully")
        
        # Test enum values
        assert CylinderLifecycleState.NEW == "new"
        assert CylinderCondition.EXCELLENT == "excellent"
        assert MaintenanceType.ROUTINE_INSPECTION == "routine_inspection"
        assert QualityCheckStatus.PASSED == "passed"
        
        print("✅ Enum values are correct")
        
        # Test that we can access enum members without TypeError
        lifecycle_states = list(CylinderLifecycleState)
        conditions = list(CylinderCondition)
        
        print(f"✅ CylinderLifecycleState has {len(lifecycle_states)} states")
        print(f"✅ CylinderCondition has {len(conditions)} conditions")
        
        print("✅ SQLAlchemy Enum tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ SQLAlchemy Enum test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_shared_models():
    """Test shared models import."""
    print("\n🧪 Testing shared models...")
    
    try:
        from shared.models import CylinderSize, UserRole
        from shared.security.auth import get_current_user
        
        print("✅ Shared models imported successfully")
        print("✅ Authentication function imported successfully")
        
        # Test enum values
        assert hasattr(CylinderSize, 'SMALL')
        assert hasattr(UserRole, 'VENDOR')
        
        print("✅ Shared models tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Shared models test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Running inventory service fix verification tests...\n")
    
    tests = [
        test_pydantic_validation,
        test_authentication_imports,
        test_sqlalchemy_enum_models,
        test_shared_models
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All fixes are working correctly!")
        return 0
    else:
        print("⚠️  Some tests failed - fixes may need attention")
        return 1

if __name__ == "__main__":
    exit(main())
