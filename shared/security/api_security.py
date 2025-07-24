"""
Comprehensive API security utilities for input validation, sanitization, and secure error handling.
"""

import re
import json
import html
import bleach
import validators
from typing import Any, Dict, List, Optional, Union, Callable
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator, ValidationError
from datetime import datetime, date
import logging
import traceback
import uuid
from decimal import Decimal, InvalidOperation

from .auth import security_validator
from .encryption import data_masking

logger = logging.getLogger(__name__)


class SecureValidator:
    """Enhanced input validation with security focus."""
    
    # Common validation patterns
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'phone_ng': r'^(\+234|234|0)?[789]\d{9}$',  # Nigerian phone numbers
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        'alphanumeric': r'^[a-zA-Z0-9]+$',
        'alphanumeric_space': r'^[a-zA-Z0-9\s]+$',
        'safe_text': r'^[a-zA-Z0-9\s\-_.,!?()]+$',
        'numeric': r'^\d+$',
        'decimal': r'^\d+(\.\d{1,2})?$',
        'password': r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
    }
    
    # Dangerous patterns to reject
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript protocol
        r'vbscript:',  # VBScript protocol
        r'on\w+\s*=',  # Event handlers
        r'expression\s*\(',  # CSS expressions
        r'@import',  # CSS imports
        r'<iframe[^>]*>',  # Iframes
        r'<object[^>]*>',  # Objects
        r'<embed[^>]*>',  # Embeds
        r'<link[^>]*>',  # Links
        r'<meta[^>]*>',  # Meta tags
    ]
    
    @classmethod
    def validate_string(
        cls,
        value: str,
        min_length: int = 0,
        max_length: int = 1000,
        pattern: str = None,
        allow_empty: bool = False,
        sanitize: bool = True
    ) -> str:
        """Validate and sanitize string input."""
        
        if value is None:
            if allow_empty:
                return ""
            raise ValueError("Value cannot be None")
        
        if not isinstance(value, str):
            value = str(value)
        
        # Check for dangerous patterns
        for dangerous_pattern in cls.DANGEROUS_PATTERNS:
            if re.search(dangerous_pattern, value, re.IGNORECASE):
                raise ValueError("Input contains potentially dangerous content")
        
        # Sanitize if requested
        if sanitize:
            value = cls.sanitize_string(value)
        
        # Check length
        if len(value) < min_length:
            raise ValueError(f"Value must be at least {min_length} characters long")
        
        if len(value) > max_length:
            raise ValueError(f"Value must be at most {max_length} characters long")
        
        # Check pattern
        if pattern:
            if pattern in cls.PATTERNS:
                pattern = cls.PATTERNS[pattern]
            
            if not re.match(pattern, value):
                raise ValueError(f"Value does not match required pattern")
        
        return value
    
    @classmethod
    def sanitize_string(cls, value: str) -> str:
        """Sanitize string input to remove dangerous content."""
        
        if not isinstance(value, str):
            return str(value)
        
        # HTML escape
        value = html.escape(value)
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Clean with bleach (allows only safe HTML)
        allowed_tags = []  # No HTML tags allowed
        allowed_attributes = {}
        
        value = bleach.clean(
            value,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
        
        # Remove excessive whitespace
        value = re.sub(r'\s+', ' ', value).strip()
        
        return value
    
    @classmethod
    def validate_email(cls, email: str) -> str:
        """Validate email address."""
        
        email = cls.validate_string(email, max_length=254, pattern='email')
        
        # Additional validation using validators library
        if not validators.email(email):
            raise ValueError("Invalid email format")
        
        return email.lower()
    
    @classmethod
    def validate_phone(cls, phone: str, country_code: str = 'NG') -> str:
        """Validate phone number."""
        
        phone = cls.validate_string(phone, max_length=20)
        
        # Remove all non-digit characters for validation
        digits_only = re.sub(r'\D', '', phone)
        
        if country_code == 'NG':
            if not re.match(cls.PATTERNS['phone_ng'], digits_only):
                raise ValueError("Invalid Nigerian phone number format")
            
            # Normalize to international format
            if digits_only.startswith('0'):
                digits_only = '234' + digits_only[1:]
            elif not digits_only.startswith('234'):
                digits_only = '234' + digits_only
        
        return '+' + digits_only
    
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        """Validate UUID format."""
        
        value = cls.validate_string(value, pattern='uuid')
        
        try:
            uuid.UUID(value)
        except ValueError:
            raise ValueError("Invalid UUID format")
        
        return value
    
    @classmethod
    def validate_decimal(cls, value: Union[str, float, Decimal], min_value: float = None, max_value: float = None) -> Decimal:
        """Validate decimal/monetary values."""
        
        try:
            if isinstance(value, str):
                # Remove currency symbols and spaces
                value = re.sub(r'[^\d.-]', '', value)
            
            decimal_value = Decimal(str(value))
            
            if min_value is not None and decimal_value < Decimal(str(min_value)):
                raise ValueError(f"Value must be at least {min_value}")
            
            if max_value is not None and decimal_value > Decimal(str(max_value)):
                raise ValueError(f"Value must be at most {max_value}")
            
            return decimal_value
            
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"Invalid decimal value: {str(e)}")
    
    @classmethod
    def validate_date(cls, value: Union[str, datetime, date]) -> date:
        """Validate date input."""
        
        if isinstance(value, date):
            return value
        
        if isinstance(value, datetime):
            return value.date()
        
        if isinstance(value, str):
            try:
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        parsed_date = datetime.strptime(value, fmt)
                        return parsed_date.date()
                    except ValueError:
                        continue
                
                raise ValueError("Unable to parse date")
                
            except ValueError:
                raise ValueError("Invalid date format")
        
        raise ValueError("Invalid date type")
    
    @classmethod
    def validate_json(cls, value: str, max_size: int = 10000) -> Dict[str, Any]:
        """Validate and parse JSON input."""
        
        if not isinstance(value, str):
            raise ValueError("JSON input must be a string")
        
        if len(value) > max_size:
            raise ValueError(f"JSON input too large (max {max_size} characters)")
        
        try:
            parsed = json.loads(value)
            
            # Check for dangerous content in JSON
            cls._validate_json_content(parsed)
            
            return parsed
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {str(e)}")
    
    @classmethod
    def _validate_json_content(cls, obj: Any, depth: int = 0) -> None:
        """Recursively validate JSON content for dangerous patterns."""
        
        if depth > 10:  # Prevent deep recursion
            raise ValueError("JSON structure too deep")
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(key, str):
                    cls.validate_string(key, max_length=100)
                cls._validate_json_content(value, depth + 1)
        
        elif isinstance(obj, list):
            if len(obj) > 1000:  # Prevent large arrays
                raise ValueError("JSON array too large")
            
            for item in obj:
                cls._validate_json_content(item, depth + 1)
        
        elif isinstance(obj, str):
            cls.validate_string(obj, max_length=10000)


class SecureErrorHandler:
    """Secure error handling that doesn't expose sensitive information."""
    
    @staticmethod
    def handle_validation_error(error: ValidationError) -> JSONResponse:
        """Handle Pydantic validation errors securely."""
        
        # Extract safe error messages
        safe_errors = []
        
        for error_detail in error.errors():
            field = ".".join(str(loc) for loc in error_detail["loc"])
            message = error_detail["msg"]
            
            # Sanitize error message
            safe_message = SecureValidator.sanitize_string(message)
            
            safe_errors.append({
                "field": field,
                "message": safe_message,
                "type": error_detail["type"]
            })
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation failed",
                "details": safe_errors,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def handle_generic_error(
        error: Exception,
        request: Request = None,
        expose_details: bool = False
    ) -> JSONResponse:
        """Handle generic errors securely."""
        
        # Log the full error for debugging
        error_id = str(uuid.uuid4())
        
        logger.error(
            f"Error ID {error_id}: {str(error)}",
            extra={
                "error_id": error_id,
                "error_type": type(error).__name__,
                "traceback": traceback.format_exc(),
                "request_path": str(request.url.path) if request else None,
                "request_method": request.method if request else None
            }
        )
        
        # Determine response based on error type
        if isinstance(error, HTTPException):
            status_code = error.status_code
            message = error.detail
        elif isinstance(error, ValueError):
            status_code = status.HTTP_400_BAD_REQUEST
            message = str(error) if expose_details else "Invalid input provided"
        elif isinstance(error, PermissionError):
            status_code = status.HTTP_403_FORBIDDEN
            message = "Access denied"
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            message = "An internal error occurred"
        
        # Sanitize message
        safe_message = SecureValidator.sanitize_string(message)
        
        response_content = {
            "error": safe_message,
            "error_id": error_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add details only in development
        if expose_details and isinstance(error, Exception):
            response_content["details"] = str(error)
        
        return JSONResponse(
            status_code=status_code,
            content=response_content
        )


class RequestValidator:
    """Request-level validation and security checks."""
    
    @staticmethod
    def validate_content_type(request: Request, allowed_types: List[str] = None) -> bool:
        """Validate request content type."""
        
        if allowed_types is None:
            allowed_types = ["application/json", "multipart/form-data"]
        
        content_type = request.headers.get("content-type", "")
        
        return any(content_type.startswith(allowed_type) for allowed_type in allowed_types)
    
    @staticmethod
    def validate_request_size(request: Request, max_size: int = 10 * 1024 * 1024) -> bool:
        """Validate request size."""
        
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                size = int(content_length)
                return size <= max_size
            except ValueError:
                return False
        
        return True
    
    @staticmethod
    def validate_user_agent(request: Request) -> bool:
        """Validate user agent header."""
        
        user_agent = request.headers.get("user-agent", "")
        
        # Check for suspicious user agents
        suspicious_patterns = [
            r'bot',
            r'crawler',
            r'spider',
            r'scraper',
            r'curl',
            r'wget',
            r'python-requests'
        ]
        
        user_agent_lower = user_agent.lower()
        
        for pattern in suspicious_patterns:
            if re.search(pattern, user_agent_lower):
                logger.warning(f"Suspicious user agent detected: {user_agent}")
                return False
        
        return True
    
    @staticmethod
    async def validate_request_body(request: Request) -> Dict[str, Any]:
        """Validate and parse request body securely."""
        
        try:
            body = await request.body()
            
            if not body:
                return {}
            
            # Check body size
            if len(body) > 10 * 1024 * 1024:  # 10MB limit
                raise ValueError("Request body too large")
            
            # Parse JSON
            if request.headers.get("content-type", "").startswith("application/json"):
                body_str = body.decode("utf-8")
                return SecureValidator.validate_json(body_str)
            
            return {}
            
        except Exception as e:
            logger.error(f"Request body validation error: {str(e)}")
            raise ValueError("Invalid request body")


# Decorator for secure API endpoints
def secure_endpoint(
    validate_content_type: bool = True,
    validate_size: bool = True,
    validate_user_agent: bool = False,
    max_request_size: int = 10 * 1024 * 1024
):
    """Decorator to add security validation to API endpoints."""
    
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Find request object in arguments
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Look in kwargs
                request = kwargs.get('request')
            
            if request:
                # Validate content type
                if validate_content_type and not RequestValidator.validate_content_type(request):
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Unsupported content type"
                    )
                
                # Validate request size
                if validate_size and not RequestValidator.validate_request_size(request, max_request_size):
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request too large"
                    )
                
                # Validate user agent
                if validate_user_agent and not RequestValidator.validate_user_agent(request):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid user agent"
                    )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
