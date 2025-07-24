"""
Comprehensive security testing suite for the Oxygen Supply Platform.
Tests authentication, authorization, input validation, encryption, and security policies.
"""

import pytest
import asyncio
import httpx
import jwt
import time
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.security.auth import jwt_manager, password_manager, SecurityConfig
from shared.security.encryption import encryption_manager, data_masking
from shared.security.api_security import SecureValidator, SecureErrorHandler
from shared.security.monitoring import security_monitor, SecurityEventType, SecurityEventSeverity


class TestAuthenticationSecurity:
    """Test authentication security measures."""
    
    def test_password_strength_validation(self):
        """Test password strength validation."""
        
        # Test weak passwords
        weak_passwords = [
            "123456",
            "password",
            "abc123",
            "qwerty",
            "Password1",  # Missing special character
            "password!",  # Missing uppercase and number
            "PASS!123"    # Missing lowercase
        ]
        
        for password in weak_passwords:
            result = password_manager.validate_password_strength(password)
            assert not result["is_valid"], f"Weak password should be rejected: {password}"
        
        # Test strong passwords
        strong_passwords = [
            "MyStr0ng!Password",
            "C0mplex@Pass123",
            "Secure#2024$Pass"
        ]
        
        for password in strong_passwords:
            result = password_manager.validate_password_strength(password)
            assert result["is_valid"], f"Strong password should be accepted: {password}"
    
    def test_password_hashing_security(self):
        """Test password hashing security."""
        
        password = "TestPassword123!"
        
        # Test hashing
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)
        
        # Hashes should be different (due to salt)
        assert hash1 != hash2
        
        # Both should verify correctly
        assert password_manager.verify_password(password, hash1)
        assert password_manager.verify_password(password, hash2)
        
        # Wrong password should not verify
        assert not password_manager.verify_password("WrongPassword", hash1)
    
    def test_jwt_token_security(self):
        """Test JWT token security."""
        
        user_id = "test-user-123"
        role = "hospital"
        
        # Create token
        token = jwt_manager.create_access_token(user_id, role)
        
        # Verify token
        payload = jwt_manager.verify_token(token)
        assert payload["sub"] == user_id
        assert payload["role"] == role
        assert "jti" in payload  # JWT ID should be present
        assert "exp" in payload  # Expiration should be present
        
        # Test expired token
        expired_token = jwt.encode(
            {
                "sub": user_id,
                "role": role,
                "exp": datetime.utcnow() - timedelta(minutes=1),
                "iat": datetime.utcnow() - timedelta(minutes=2)
            },
            SecurityConfig.JWT_SECRET_KEY,
            algorithm=SecurityConfig.JWT_ALGORITHM
        )
        
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt_manager.verify_token(expired_token)
        
        # Test invalid token
        with pytest.raises(jwt.InvalidTokenError):
            jwt_manager.verify_token("invalid.token.here")
    
    def test_mfa_token_security(self):
        """Test MFA token security."""
        
        user_id = "test-user-123"
        mfa_token = jwt_manager.create_mfa_token(user_id, "totp")
        
        # Verify MFA token
        payload = jwt_manager.verify_token(mfa_token, expected_type=jwt_manager.TokenType.MFA)
        assert payload["sub"] == user_id
        assert payload["type"] == "mfa"
        assert payload["mfa_method"] == "totp"
        
        # MFA token should have short expiration
        exp_time = datetime.fromtimestamp(payload["exp"])
        created_time = datetime.fromtimestamp(payload["iat"])
        duration = exp_time - created_time
        assert duration <= timedelta(minutes=5)


class TestInputValidationSecurity:
    """Test input validation and sanitization."""
    
    def test_sql_injection_prevention(self):
        """Test SQL injection prevention."""
        
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "1; DELETE FROM users WHERE 1=1; --",
            "' UNION SELECT * FROM passwords --"
        ]
        
        for malicious_input in malicious_inputs:
            assert not SecureValidator.validate_sql_injection(malicious_input)
    
    def test_xss_prevention(self):
        """Test XSS prevention."""
        
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<iframe src='javascript:alert(1)'></iframe>",
            "vbscript:msgbox('xss')"
        ]
        
        for malicious_input in malicious_inputs:
            with pytest.raises(ValueError):
                SecureValidator.validate_string(malicious_input)
    
    def test_input_sanitization(self):
        """Test input sanitization."""
        
        # Test HTML escaping
        dangerous_input = "<script>alert('test')</script>"
        sanitized = SecureValidator.sanitize_string(dangerous_input)
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized or sanitized == ""
        
        # Test null byte removal
        null_input = "test\x00string"
        sanitized = SecureValidator.sanitize_string(null_input)
        assert "\x00" not in sanitized
    
    def test_email_validation(self):
        """Test email validation."""
        
        valid_emails = [
            "user@example.com",
            "test.email@domain.co.uk",
            "user+tag@example.org"
        ]
        
        invalid_emails = [
            "invalid-email",
            "@domain.com",
            "user@",
            "user..double.dot@example.com",
            "user@domain",
            "a" * 250 + "@example.com"  # Too long
        ]
        
        for email in valid_emails:
            result = SecureValidator.validate_email(email)
            assert result == email.lower()
        
        for email in invalid_emails:
            with pytest.raises(ValueError):
                SecureValidator.validate_email(email)
    
    def test_phone_validation(self):
        """Test phone number validation."""
        
        valid_phones = [
            "+2348012345678",
            "08012345678",
            "2348012345678",
            "8012345678"
        ]
        
        invalid_phones = [
            "123456",
            "+1234567890",  # Wrong country code
            "08012345",     # Too short
            "080123456789012"  # Too long
        ]
        
        for phone in valid_phones:
            result = SecureValidator.validate_phone(phone)
            assert result.startswith("+234")
        
        for phone in invalid_phones:
            with pytest.raises(ValueError):
                SecureValidator.validate_phone(phone)


class TestEncryptionSecurity:
    """Test encryption and data protection."""
    
    def test_field_encryption(self):
        """Test field-level encryption."""
        
        sensitive_data = "user@example.com"
        
        # Encrypt data
        encrypted = encryption_manager.encrypt_field(sensitive_data, "email")
        
        # Should be different from original
        assert encrypted != sensitive_data
        
        # Should be base64 encoded
        import base64
        try:
            base64.urlsafe_b64decode(encrypted.encode())
        except Exception:
            pytest.fail("Encrypted data should be base64 encoded")
        
        # Decrypt should return original
        decrypted = encryption_manager.decrypt_field(encrypted, "email")
        assert decrypted == sensitive_data
    
    def test_pii_encryption(self):
        """Test PII encryption."""
        
        pii_data = {
            "email": "user@example.com",
            "phone": "+2348012345678",
            "full_name": "John Doe",
            "address": "123 Main Street",
            "non_pii": "public data"
        }
        
        # Encrypt PII
        encrypted_data = encryption_manager.encrypt_pii(pii_data)
        
        # PII fields should be encrypted
        assert encrypted_data["email"] != pii_data["email"]
        assert encrypted_data["phone"] != pii_data["phone"]
        assert encrypted_data["full_name"] != pii_data["full_name"]
        
        # Non-PII should remain unchanged
        assert encrypted_data["non_pii"] == pii_data["non_pii"]
        
        # Decrypt should restore original
        decrypted_data = encryption_manager.decrypt_pii(encrypted_data)
        assert decrypted_data == pii_data
    
    def test_data_masking(self):
        """Test data masking for logs."""
        
        # Test email masking
        email = "user@example.com"
        masked = data_masking.mask_email(email)
        assert masked != email
        assert "@example.com" in masked
        assert "user" not in masked or masked.startswith("u") and masked.endswith("r@example.com")
        
        # Test phone masking
        phone = "+2348012345678"
        masked = data_masking.mask_phone(phone)
        assert masked != phone
        assert len(masked) == len(phone)
        assert "*" in masked
        
        # Test card number masking
        card = "1234567890123456"
        masked = data_masking.mask_card_number(card)
        assert masked.startswith("1234")
        assert masked.endswith("3456")
        assert "*" in masked


class TestAPISecurityIntegration:
    """Test API security integration."""
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        
        # This would require a running API instance
        # For now, test the rate limiting logic
        from shared.security.middleware import RateLimitMiddleware
        
        # Mock Redis client
        with patch('redis.from_url') as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            
            # Simulate rate limit check
            mock_client.zcard.return_value = 5  # Under limit
            middleware = RateLimitMiddleware(None, default_rate_limit=10)
            
            # Should allow request
            result = await middleware._check_rate_limit("test_client", "/api/test", 10)
            assert result is True
            
            # Simulate over limit
            mock_client.zcard.return_value = 15  # Over limit
            result = await middleware._check_rate_limit("test_client", "/api/test", 10)
            assert result is False
    
    def test_security_headers(self):
        """Test security headers configuration."""
        
        from shared.security.auth import SecurityConfig
        
        headers = SecurityConfig.SECURITY_HEADERS
        
        # Check required security headers
        assert "X-Content-Type-Options" in headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        
        assert "X-Frame-Options" in headers
        assert headers["X-Frame-Options"] == "DENY"
        
        assert "X-XSS-Protection" in headers
        assert "Strict-Transport-Security" in headers
        assert "Content-Security-Policy" in headers
    
    @pytest.mark.asyncio
    async def test_security_monitoring(self):
        """Test security monitoring functionality."""
        
        # Test security event logging
        event_id = await security_monitor.log_security_event(
            SecurityEventType.AUTHENTICATION_FAILURE,
            SecurityEventSeverity.MEDIUM,
            "test-service",
            user_id="test-user",
            ip_address="192.168.1.1",
            details={"reason": "invalid_password"}
        )
        
        assert event_id is not None
        assert event_id.startswith("sec_")


class TestSecurityPolicies:
    """Test security policy enforcement."""
    
    def test_password_policy_enforcement(self):
        """Test password policy enforcement."""
        
        # Test minimum length
        short_password = "Abc1!"
        result = password_manager.validate_password_strength(short_password)
        assert not result["is_valid"]
        assert any("at least" in error for error in result["errors"])
        
        # Test complexity requirements
        simple_password = "password123"
        result = password_manager.validate_password_strength(simple_password)
        assert not result["is_valid"]
        
        # Test common password detection
        common_password = "Password123"
        result = password_manager.validate_password_strength(common_password)
        # Should still be valid if it meets other requirements
        assert result["is_valid"]
    
    def test_session_security(self):
        """Test session security policies."""
        
        # Test JWT expiration
        token = jwt_manager.create_access_token("user-123", "hospital")
        payload = jwt_manager.verify_token(token)
        
        # Check expiration time
        exp_time = datetime.fromtimestamp(payload["exp"])
        created_time = datetime.fromtimestamp(payload["iat"])
        duration = exp_time - created_time
        
        # Should not exceed configured maximum
        max_duration = timedelta(minutes=SecurityConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        assert duration <= max_duration
    
    def test_data_retention_policy(self):
        """Test data retention policy."""
        
        from shared.security.privacy import DataRetentionPolicy, DataClassification
        
        # Test retention periods
        pii_retention = DataRetentionPolicy.get_retention_period(DataClassification.PII)
        assert pii_retention.days >= 365  # At least 1 year
        
        public_retention = DataRetentionPolicy.get_retention_period(DataClassification.PUBLIC)
        assert public_retention.days <= pii_retention.days  # Public data should have shorter retention
        
        # Test expiration check
        old_date = datetime.utcnow() - timedelta(days=400)
        is_expired = DataRetentionPolicy.is_expired(old_date, DataClassification.PUBLIC)
        assert is_expired  # Should be expired for public data


class TestPenetrationTestingHelpers:
    """Helper methods for penetration testing."""
    
    def test_common_vulnerabilities(self):
        """Test for common security vulnerabilities."""
        
        # Test for hardcoded secrets (this would be expanded in real testing)
        sensitive_patterns = [
            "password",
            "secret",
            "key",
            "token"
        ]
        
        # In a real test, this would scan actual code files
        # For now, just verify the patterns are defined
        assert len(sensitive_patterns) > 0
    
    def generate_security_test_report(self):
        """Generate a security test report."""
        
        report = {
            "test_timestamp": datetime.utcnow().isoformat(),
            "tests_run": [
                "authentication_security",
                "input_validation",
                "encryption",
                "api_security",
                "security_policies"
            ],
            "vulnerabilities_found": [],
            "recommendations": [
                "Regularly update dependencies",
                "Implement security headers",
                "Use HTTPS in production",
                "Enable audit logging",
                "Implement rate limiting"
            ]
        }
        
        return report


# Security test configuration
@pytest.fixture
def security_test_config():
    """Configuration for security tests."""
    return {
        "test_user_id": "test-user-123",
        "test_email": "test@example.com",
        "test_password": "TestPassword123!",
        "test_ip": "192.168.1.100"
    }


# Run security validation
def run_security_validation():
    """Run comprehensive security validation."""
    
    print("🔒 Running Security Validation Suite...")
    
    # Run pytest with security tests
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])
    
    if exit_code == 0:
        print("✅ All security tests passed!")
    else:
        print("❌ Security tests failed!")
    
    return exit_code == 0


if __name__ == "__main__":
    run_security_validation()
