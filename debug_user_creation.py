#!/usr/bin/env python3
"""
Debug script to test user creation directly
"""

import sys
import os

# Set environment variables to avoid config issues
os.environ['DATABASE_URL'] = 'postgresql://user:password@localhost:5432/oxygen_platform'
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'

# Add the user-service directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'user-service'))

def test_user_creation():
    """Test user creation to debug the issue."""

    try:
        # Import the User model
        from app.models.user import User
        from shared.models import UserRole

        print("✓ Successfully imported User model")
        print(f"User model columns: {[col.name for col in User.__table__.columns]}")

        # Try to create a User instance
        user = User(
            email="debug@test.com",
            password_hash="test_hash",
            role=UserRole.HOSPITAL
        )

        print("✓ Successfully created User instance")
        print(f"User email: {user.email}")
        print(f"User password_hash: {user.password_hash}")
        print(f"User role: {user.role}")

        # Test with hashed_password to see if that's the issue
        try:
            user2 = User(
                email="debug2@test.com",
                hashed_password="test_hash",
                role=UserRole.HOSPITAL
            )
            print("✗ User model accepts 'hashed_password' - this is the problem!")
        except Exception as e:
            print(f"✓ User model correctly rejects 'hashed_password': {e}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_user_creation()
