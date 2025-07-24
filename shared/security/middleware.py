"""
Security middleware for rate limiting, request validation, and security headers.
"""

import time
import json
import hashlib
from typing import Dict, Any, Optional, Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis
import logging
from datetime import datetime, timedelta
import ipaddress
import re

from .auth import SecurityConfig, security_validator

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with Redis backend."""
    
    def __init__(
        self, 
        app,
        redis_url: str = "redis://localhost:6379",
        default_rate_limit: int = 60,
        rate_limit_window: int = 60,
        burst_limit: int = 10
    ):
        super().__init__(app)
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.default_rate_limit = default_rate_limit
        self.rate_limit_window = rate_limit_window
        self.burst_limit = burst_limit
        
        # Different rate limits for different endpoints
        self.endpoint_limits = {
            "/auth/login": 5,  # Stricter for login
            "/auth/register": 3,  # Stricter for registration
            "/auth/forgot-password": 3,
            "/admin/": 30,  # Moderate for admin endpoints
            "/payment/": 20,  # Stricter for payment endpoints
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        
        # Get client identifier
        client_id = self._get_client_identifier(request)
        
        # Get rate limit for this endpoint
        rate_limit = self._get_rate_limit_for_endpoint(request.url.path)
        
        # Check rate limit
        if not await self._check_rate_limit(client_id, request.url.path, rate_limit):
            logger.warning(f"Rate limit exceeded for {client_id} on {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {rate_limit} per {self.rate_limit_window} seconds",
                    "retry_after": self.rate_limit_window
                },
                headers={"Retry-After": str(self.rate_limit_window)}
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = await self._get_remaining_requests(client_id, request.url.path, rate_limit)
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + self.rate_limit_window)
        
        return response
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier for rate limiting."""
        
        # Try to get user ID from JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from .auth import jwt_manager
                token = auth_header.split(" ")[1]
                payload = jwt_manager.verify_token(token)
                return f"user:{payload['sub']}"
            except:
                pass
        
        # Fall back to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        return f"ip:{client_ip}"
    
    def _get_rate_limit_for_endpoint(self, path: str) -> int:
        """Get rate limit for specific endpoint."""
        
        for endpoint_pattern, limit in self.endpoint_limits.items():
            if path.startswith(endpoint_pattern):
                return limit
        
        return self.default_rate_limit
    
    async def _check_rate_limit(self, client_id: str, endpoint: str, limit: int) -> bool:
        """Check if client has exceeded rate limit."""
        
        key = f"rate_limit:{client_id}:{endpoint}"
        current_time = int(time.time())
        window_start = current_time - self.rate_limit_window
        
        try:
            # Use Redis sorted set to track requests in time window
            pipe = self.redis_client.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, self.rate_limit_window)
            
            results = pipe.execute()
            current_requests = results[1]
            
            return current_requests < limit
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            # Allow request if Redis is down
            return True
    
    async def _get_remaining_requests(self, client_id: str, endpoint: str, limit: int) -> int:
        """Get remaining requests for client."""
        
        key = f"rate_limit:{client_id}:{endpoint}"
        current_time = int(time.time())
        window_start = current_time - self.rate_limit_window
        
        try:
            # Clean old entries and count current
            self.redis_client.zremrangebyscore(key, 0, window_start)
            current_requests = self.redis_client.zcard(key)
            
            return max(0, limit - current_requests)
            
        except Exception as e:
            logger.error(f"Error getting remaining requests: {str(e)}")
            return limit


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    def __init__(self, app, additional_headers: Dict[str, str] = None):
        super().__init__(app)
        self.security_headers = SecurityConfig.SECURITY_HEADERS.copy()
        if additional_headers:
            self.security_headers.update(additional_headers)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value
        
        # Remove server header for security
        if "server" in response.headers:
            del response.headers["server"]
        
        return response


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for input validation and sanitization."""
    
    def __init__(self, app, max_request_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_request_size = max_request_size
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate and sanitize request input."""
        
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_request_size:
            logger.warning(f"Request too large: {content_length} bytes from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": "Request too large",
                    "message": f"Request size exceeds maximum allowed size of {self.max_request_size} bytes"
                }
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "")
            if not self._is_allowed_content_type(content_type):
                logger.warning(f"Invalid content type: {content_type} from {request.client.host}")
                return JSONResponse(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    content={
                        "error": "Unsupported media type",
                        "message": "Content-Type must be application/json or multipart/form-data"
                    }
                )
        
        # Check for suspicious patterns in URL
        if not self._validate_url_path(request.url.path):
            logger.warning(f"Suspicious URL pattern detected: {request.url.path} from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Invalid request",
                    "message": "Request contains invalid characters"
                }
            )
        
        # Validate query parameters
        for key, value in request.query_params.items():
            if not security_validator.validate_sql_injection(f"{key}={value}"):
                logger.warning(f"Potential SQL injection in query params: {key}={value} from {request.client.host}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": "Invalid request",
                        "message": "Request contains invalid parameters"
                    }
                )
        
        return await call_next(request)
    
    def _is_allowed_content_type(self, content_type: str) -> bool:
        """Check if content type is allowed."""
        allowed_types = [
            "application/json",
            "multipart/form-data",
            "application/x-www-form-urlencoded"
        ]
        
        return any(content_type.startswith(allowed_type) for allowed_type in allowed_types)
    
    def _validate_url_path(self, path: str) -> bool:
        """Validate URL path for suspicious patterns."""
        
        # Check for path traversal attempts
        if ".." in path or "~" in path:
            return False
        
        # Check for null bytes
        if "\x00" in path:
            return False
        
        # Check for script injection attempts
        suspicious_patterns = [
            r'<script',
            r'javascript:',
            r'vbscript:',
            r'onload=',
            r'onerror=',
            r'eval\(',
            r'expression\('
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, path, re.IGNORECASE):
                return False
        
        return True


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Middleware for IP whitelisting (optional for admin endpoints)."""
    
    def __init__(self, app, whitelist: list = None, admin_only: bool = True):
        super().__init__(app)
        self.whitelist = whitelist or []
        self.admin_only = admin_only
        
        # Convert string IPs to IP network objects
        self.allowed_networks = []
        for ip in self.whitelist:
            try:
                self.allowed_networks.append(ipaddress.ip_network(ip, strict=False))
            except ValueError:
                logger.error(f"Invalid IP address in whitelist: {ip}")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check IP whitelist for admin endpoints."""
        
        # Only apply to admin endpoints if admin_only is True
        if self.admin_only and not request.url.path.startswith("/admin/"):
            return await call_next(request)
        
        # Skip if no whitelist configured
        if not self.allowed_networks:
            return await call_next(request)
        
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        try:
            client_ip_obj = ipaddress.ip_address(client_ip)
            
            # Check if IP is in whitelist
            for network in self.allowed_networks:
                if client_ip_obj in network:
                    return await call_next(request)
            
            # IP not in whitelist
            logger.warning(f"Access denied for IP {client_ip} on {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Access denied",
                    "message": "Your IP address is not authorized to access this resource"
                }
            )
            
        except ValueError:
            logger.error(f"Invalid client IP address: {client_ip}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Invalid request",
                    "message": "Unable to determine client IP address"
                }
            )
