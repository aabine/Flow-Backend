"""
Rate limiting middleware for FastAPI.
Implements request rate limiting and security headers.
"""

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import time
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.rate_limit_service import RateLimitService, RateLimitConfig


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""
    
    def __init__(self, app, excluded_paths: list = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or ["/health", "/docs", "/openapi.json", "/redoc"]
    
    def get_client_identifier(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from app.core.security import JWTManager
                token = auth_header.split(" ")[1]
                payload = JWTManager().verify_token(token)
                user_id = payload.get("user_id")
                if user_id:
                    return f"user:{user_id}"
            except:
                pass
        
        # Fall back to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        return f"ip:{client_ip}"
    
    def should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from rate limiting."""
        return any(excluded in path for excluded in self.excluded_paths)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        start_time = time.time()
        
        # Skip rate limiting for excluded paths
        if self.should_exclude_path(request.url.path):
            response = await call_next(request)
            return self.add_security_headers(response)
        
        # Get client identifier
        client_id = self.get_client_identifier(request)
        
        # Check API rate limit
        is_allowed, current_count, remaining = await RateLimitService().check_api_rate_limit(client_id)
        
        if not is_allowed:
            # Get rate limit info for headers
            rate_info = await RateLimitService().get_rate_limit_info("api", client_id)
            
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": 60  # seconds
                }
            )
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(int(rate_info["reset_time"].timestamp()) if rate_info["reset_time"] else 0)
            response.headers["Retry-After"] = "60"
            
            return self.add_security_headers(response)
        
        # Increment request counter
        await RateLimitService().increment_api_requests(client_id)
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error and return 500
            print(f"Request processing error: {e}")
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred"
                }
            )
        
        # Add rate limit headers to successful responses
        if response.status_code < 400:
            rate_info = await RateLimitService().get_rate_limit_info("api", client_id)
            response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(int(rate_info["reset_time"].timestamp()) if rate_info["reset_time"] else 0)
        
        # Add processing time header
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        return self.add_security_headers(response)
    
    def add_security_headers(self, response: Response) -> Response:
        """Add security headers to response."""
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response


class LoginRateLimitMiddleware:
    """Specific rate limiting for login endpoints."""
    
    @staticmethod
    async def check_login_rate_limit(request: Request) -> None:
        """Check login-specific rate limits."""
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        # Check IP-based rate limit
        ip_allowed, ip_count, ip_remaining = await RateLimitService().check_login_rate_limit(f"ip:{client_ip}")
        
        if not ip_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts from this IP address. Please try again later.",
                headers={
                    "Retry-After": "900",  # 15 minutes
                    "X-RateLimit-Limit": str(RateLimitService().config.LOGIN_MAX_ATTEMPTS),
                    "X-RateLimit-Remaining": str(ip_remaining)
                }
            )
        
        # For login attempts, also check email-based rate limit if email is provided
        try:
            if request.method == "POST":
                body = await request.body()
                if body:
                    import json
                    data = json.loads(body)
                    email = data.get("email")
                    
                    if email:
                        email_allowed, email_count, email_remaining = await RateLimitService().check_login_rate_limit(f"email:{email}")
                        
                        if not email_allowed:
                            raise HTTPException(
                                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many login attempts for this email. Please try again later.",
                                headers={
                                    "Retry-After": "900",  # 15 minutes
                                    "X-RateLimit-Limit": str(RateLimitService().config.LOGIN_MAX_ATTEMPTS),
                                    "X-RateLimit-Remaining": str(email_remaining)
                                }
                            )
        except:
            # If we can't parse the body, just continue with IP-based limiting
            pass


class PasswordResetRateLimitMiddleware:
    """Rate limiting for password reset endpoints."""
    
    @staticmethod
    async def check_password_reset_rate_limit(request: Request) -> None:
        """Check password reset rate limits."""
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        # Check IP-based rate limit
        ip_allowed, ip_count, ip_remaining = await RateLimitService().check_password_reset_rate_limit(f"ip:{client_ip}")
        
        if not ip_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password reset attempts. Please try again later.",
                headers={
                    "Retry-After": "3600",  # 1 hour
                    "X-RateLimit-Limit": str(RateLimitService().config.PASSWORD_RESET_MAX_ATTEMPTS),
                    "X-RateLimit-Remaining": str(ip_remaining)
                }
            )


class RegistrationRateLimitMiddleware:
    """Rate limiting for registration endpoints."""

    @staticmethod
    async def check_registration_rate_limit(request: Request) -> None:
        """Check registration rate limits."""
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host

        # Check IP-based rate limit for registration
        ip_allowed, ip_count, ip_remaining = await RateLimitService().check_registration_rate_limit(f"ip:{client_ip}")

        if not ip_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts from this IP address. Please try again later.",
                headers={
                    "Retry-After": "3600",  # 1 hour
                    "X-RateLimit-Limit": "5",  # 5 registrations per hour per IP
                    "X-RateLimit-Remaining": str(ip_remaining)
                }
            )


class EmailVerificationRateLimitMiddleware:
    """Rate limiting for email verification endpoints."""
    
    @staticmethod
    async def check_email_verification_rate_limit(request: Request) -> None:
        """Check email verification rate limits."""
        # Get client IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host
        
        # Check IP-based rate limit
        ip_allowed, ip_count, ip_remaining = await RateLimitService().check_email_verification_rate_limit(f"ip:{client_ip}")
        
        if not ip_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many email verification attempts. Please try again later.",
                headers={
                    "Retry-After": "3600",  # 1 hour
                    "X-RateLimit-Limit": str(RateLimitService().config.EMAIL_VERIFICATION_MAX_ATTEMPTS),
                    "X-RateLimit-Remaining": str(ip_remaining)
                }
            )
