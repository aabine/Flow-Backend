"""
Rate Limiting Middleware for Flow-Backend Services
Implements Redis-based rate limiting with configurable limits per endpoint and user
"""

import time
import redis
import json
from typing import Dict, Optional, Callable, Any
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-based rate limiter with sliding window algorithm."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")  # Use DB 1 for rate limiting
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.default_limit = int(os.getenv("MAX_REQUESTS_PER_MINUTE", "100"))
        self.window_size = 60  # 1 minute window
        self._redis_client = None
        
        # Rate limits per endpoint pattern
        self.endpoint_limits = {
            "/auth/login": 5,  # 5 login attempts per minute
            "/auth/register": 3,  # 3 registration attempts per minute
            "/orders/direct": 10,  # 10 direct orders per minute
            "/orders/pricing": 20,  # 20 pricing requests per minute
            "/inventory/reservations": 15,  # 15 reservations per minute
            "/vendors/*/availability": 30,  # 30 availability checks per minute
            "/catalog/nearby": 50,  # 50 catalog searches per minute
        }
        
        # Rate limits per user role
        self.role_limits = {
            "HOSPITAL": 200,  # Hospitals get higher limits
            "VENDOR": 150,   # Vendors get moderate limits
            "ADMIN": 500,    # Admins get highest limits
            "SERVICE": 1000, # Service-to-service gets very high limits
        }
    
    def get_redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                self._redis_client.ping()
            except Exception as e:
                logger.error(f"Failed to connect to Redis for rate limiting: {str(e)}")
                self._redis_client = None
        return self._redis_client
    
    def get_rate_limit(self, endpoint: str, user_role: str = None) -> int:
        """Get rate limit for specific endpoint and user role."""
        # Check endpoint-specific limits first
        for pattern, limit in self.endpoint_limits.items():
            if pattern.replace("*", "") in endpoint:
                return limit
        
        # Check role-based limits
        if user_role and user_role in self.role_limits:
            return self.role_limits[user_role]
        
        # Return default limit
        return self.default_limit
    
    def get_rate_limit_key(self, identifier: str, endpoint: str) -> str:
        """Generate rate limit key for Redis."""
        # Normalize endpoint path
        endpoint_key = endpoint.replace("/", "_").replace("{", "").replace("}", "")
        return f"rate_limit:{identifier}:{endpoint_key}"
    
    async def is_allowed(self, request: Request, user_context: Optional[Dict[str, Any]] = None) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed based on rate limits.
        
        Returns:
            tuple: (is_allowed, rate_limit_info)
        """
        if not self.enabled:
            return True, {}
        
        client = self.get_redis_client()
        if not client:
            # If Redis is unavailable, allow the request but log warning
            logger.warning("Redis unavailable for rate limiting, allowing request")
            return True, {}
        
        # Get identifier (user ID or IP address)
        identifier = "anonymous"
        user_role = None
        
        if user_context:
            identifier = str(user_context.get("user_id", request.client.host))
            user_role = str(user_context.get("role", "")).replace("UserRole.", "")
        else:
            identifier = request.client.host
        
        endpoint = request.url.path
        rate_limit = self.get_rate_limit(endpoint, user_role)
        key = self.get_rate_limit_key(identifier, endpoint)
        
        current_time = int(time.time())
        window_start = current_time - self.window_size
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = client.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, self.window_size * 2)
            
            results = pipe.execute()
            current_requests = results[1]
            
            rate_limit_info = {
                "limit": rate_limit,
                "remaining": max(0, rate_limit - current_requests - 1),
                "reset_time": current_time + self.window_size,
                "window_size": self.window_size
            }
            
            if current_requests >= rate_limit:
                logger.warning(
                    f"Rate limit exceeded for {identifier} on {endpoint}",
                    extra={
                        "identifier": identifier,
                        "endpoint": endpoint,
                        "current_requests": current_requests,
                        "rate_limit": rate_limit,
                        "user_role": user_role
                    }
                )
                return False, rate_limit_info
            
            return True, rate_limit_info
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            # On error, allow the request
            return True, {}


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""
    
    def __init__(self, app, rate_limiter: RateLimiter = None):
        self.app = app
        self.rate_limiter = rate_limiter or RateLimiter()
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request = Request(scope, receive)
        
        # Skip rate limiting for health checks and internal endpoints
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            await self.app(scope, receive, send)
            return
        
        # Extract user context from headers (set by authentication middleware)
        user_context = None
        if "x-user-id" in request.headers:
            user_context = {
                "user_id": request.headers.get("x-user-id"),
                "role": request.headers.get("x-user-role")
            }
        
        # Check rate limit
        is_allowed, rate_limit_info = await self.rate_limiter.is_allowed(request, user_context)
        
        if not is_allowed:
            # Return rate limit exceeded response
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {rate_limit_info.get('limit')} per minute",
                    "retry_after": rate_limit_info.get('window_size', 60)
                },
                headers={
                    "X-RateLimit-Limit": str(rate_limit_info.get('limit', 0)),
                    "X-RateLimit-Remaining": str(rate_limit_info.get('remaining', 0)),
                    "X-RateLimit-Reset": str(rate_limit_info.get('reset_time', 0)),
                    "Retry-After": str(rate_limit_info.get('window_size', 60))
                }
            )
            await response(scope, receive, send)
            return
        
        # Add rate limit headers to response
        async def send_wrapper(message):
            if message["type"] == "http.response.start" and rate_limit_info:
                headers = dict(message.get("headers", []))
                headers.update({
                    b"x-ratelimit-limit": str(rate_limit_info.get('limit', 0)).encode(),
                    b"x-ratelimit-remaining": str(rate_limit_info.get('remaining', 0)).encode(),
                    b"x-ratelimit-reset": str(rate_limit_info.get('reset_time', 0)).encode()
                })
                message["headers"] = list(headers.items())
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


# Global rate limiter instance
rate_limiter = RateLimiter()
