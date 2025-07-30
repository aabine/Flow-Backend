"""
Security Middleware for Flow-Backend Services
Implements request size limiting, security headers, and other security measures
"""

import os
import logging
from typing import Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for request validation and security headers."""
    
    def __init__(self, app, **kwargs):
        super().__init__(app)
        
        # Configuration
        self.max_request_size = int(os.getenv("MAX_REQUEST_SIZE_MB", "10")) * 1024 * 1024  # 10MB default
        self.enable_security_headers = os.getenv("ENABLE_SECURITY_HEADERS", "true").lower() == "true"
        self.https_only = os.getenv("HTTPS_ONLY", "false").lower() == "true"
        self.allowed_hosts = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
        
        # Security headers configuration
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }
        
        if self.https_only:
            self.security_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add security measures."""
        
        # 1. Host validation
        if not self._validate_host(request):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid host header"}
            )
        
        # 2. HTTPS enforcement
        if self.https_only and request.url.scheme != "https":
            # Redirect to HTTPS
            https_url = request.url.replace(scheme="https")
            return JSONResponse(
                status_code=status.HTTP_301_MOVED_PERMANENTLY,
                headers={"Location": str(https_url)},
                content={"message": "Redirecting to HTTPS"}
            )
        
        # 3. Request size validation
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    logger.warning(
                        f"Request size too large: {size} bytes (max: {self.max_request_size})",
                        extra={
                            "client_ip": request.client.host,
                            "endpoint": request.url.path,
                            "request_size": size,
                            "max_size": self.max_request_size
                        }
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "Request entity too large",
                            "max_size_mb": self.max_request_size // (1024 * 1024)
                        }
                    )
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": "Invalid content-length header"}
                )
        
        # 4. Process request
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request processing error: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error"}
            )
        
        # 5. Add security headers
        if self.enable_security_headers:
            for header, value in self.security_headers.items():
                response.headers[header] = value
        
        # 6. Add custom security headers
        response.headers["X-Service-Version"] = "1.0.0"
        response.headers["X-Request-ID"] = request.headers.get("x-request-id", "unknown")
        
        return response
    
    def _validate_host(self, request: Request) -> bool:
        """Validate host header against allowed hosts."""
        if not self.allowed_hosts:
            return True
        
        host = request.headers.get("host", "").split(":")[0]  # Remove port
        return host in self.allowed_hosts or "localhost" in self.allowed_hosts


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware for state-changing operations."""
    
    def __init__(self, app, **kwargs):
        super().__init__(app)
        self.enabled = os.getenv("CSRF_PROTECTION", "true").lower() == "true"
        self.safe_methods = {"GET", "HEAD", "OPTIONS", "TRACE"}
        self.csrf_header_name = "X-CSRF-Token"
        self.csrf_cookie_name = "csrf_token"
        
        # Endpoints that require CSRF protection
        self.protected_endpoints = {
            "/auth/login",
            "/auth/register", 
            "/orders/direct",
            "/inventory/reservations",
            "/vendors/*/update"
        }
    
    async def dispatch(self, request: Request, call_next):
        """Check CSRF token for state-changing requests."""
        
        if not self.enabled:
            return await call_next(request)
        
        # Skip CSRF check for safe methods
        if request.method in self.safe_methods:
            return await call_next(request)
        
        # Skip CSRF check for non-protected endpoints
        if not self._is_protected_endpoint(request.url.path):
            return await call_next(request)
        
        # Check CSRF token
        csrf_token_header = request.headers.get(self.csrf_header_name)
        csrf_token_cookie = request.cookies.get(self.csrf_cookie_name)
        
        if not csrf_token_header or not csrf_token_cookie:
            logger.warning(
                f"CSRF token missing for {request.method} {request.url.path}",
                extra={
                    "client_ip": request.client.host,
                    "method": request.method,
                    "endpoint": request.url.path,
                    "has_header": bool(csrf_token_header),
                    "has_cookie": bool(csrf_token_cookie)
                }
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "CSRF token required"}
            )
        
        if csrf_token_header != csrf_token_cookie:
            logger.warning(
                f"CSRF token mismatch for {request.method} {request.url.path}",
                extra={
                    "client_ip": request.client.host,
                    "method": request.method,
                    "endpoint": request.url.path
                }
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "CSRF token invalid"}
            )
        
        return await call_next(request)
    
    def _is_protected_endpoint(self, path: str) -> bool:
        """Check if endpoint requires CSRF protection."""
        for protected_path in self.protected_endpoints:
            if protected_path.replace("*", "") in path:
                return True
        return False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request/response logging."""
    
    def __init__(self, app, **kwargs):
        super().__init__(app)
        self.log_requests = os.getenv("LOG_REQUESTS", "true").lower() == "true"
        self.log_responses = os.getenv("LOG_RESPONSES", "true").lower() == "true"
        self.sensitive_headers = {"authorization", "x-api-key", "cookie", "x-csrf-token"}
        
    async def dispatch(self, request: Request, call_next):
        """Log request and response with security considerations."""
        
        if not self.log_requests:
            return await call_next(request)
        
        import time
        start_time = time.time()
        
        # Log request
        request_data = {
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host,
            "user_agent": request.headers.get("user-agent", "unknown"),
            "content_length": request.headers.get("content-length", 0),
            "headers": self._sanitize_headers(dict(request.headers))
        }
        
        logger.info("Request received", extra=request_data)
        
        # Process request
        response = await call_next(request)
        
        # Log response
        if self.log_responses:
            processing_time = time.time() - start_time
            response_data = {
                "status_code": response.status_code,
                "processing_time_ms": round(processing_time * 1000, 2),
                "response_size": response.headers.get("content-length", 0)
            }
            
            if response.status_code >= 400:
                logger.warning("Request failed", extra={**request_data, **response_data})
            else:
                logger.info("Request completed", extra={**request_data, **response_data})
        
        return response
    
    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive information from headers for logging."""
        sanitized = {}
        for key, value in headers.items():
            if key.lower() in self.sensitive_headers:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        return sanitized
