"""
Redis Caching Service for Inventory Service
Provides caching for frequently accessed data like vendor availability
"""

import json
import redis
import asyncio
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)


class CacheService:
    """Redis-based caching service with async support."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = int(os.getenv("VENDOR_CACHE_TTL_SECONDS", "1800"))  # 30 minutes
        self.price_cache_ttl = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "300"))  # 5 minutes
        self._redis_client = None
        self._connection_lock = asyncio.Lock()
    
    async def get_redis_client(self):
        """Get or create Redis client with connection pooling."""
        if self._redis_client is None:
            async with self._connection_lock:
                if self._redis_client is None:
                    try:
                        self._redis_client = redis.from_url(
                            self.redis_url,
                            decode_responses=True,
                            socket_connect_timeout=5,
                            socket_timeout=5,
                            retry_on_timeout=True,
                            health_check_interval=30
                        )
                        # Test connection
                        self._redis_client.ping()
                        logger.info("Redis connection established successfully")
                    except Exception as e:
                        logger.error(f"Failed to connect to Redis: {str(e)}")
                        self._redis_client = None
                        raise
        return self._redis_client
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        """Generate standardized cache key."""
        return f"inventory:{prefix}:{identifier}"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data by key."""
        try:
            client = await self.get_redis_client()
            cached_data = client.get(key)
            
            if cached_data:
                data = json.loads(cached_data)
                logger.debug(f"Cache hit for key: {key}")
                return data
            else:
                logger.debug(f"Cache miss for key: {key}")
                return None
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {str(e)}")
            return None
    
    async def set(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set cached data with TTL."""
        try:
            client = await self.get_redis_client()
            ttl = ttl or self.default_ttl
            
            # Add cache metadata
            cache_data = {
                "data": data,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl
            }
            
            result = client.setex(key, ttl, json.dumps(cache_data))
            logger.debug(f"Cache set for key: {key}, TTL: {ttl}s")
            return result
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        try:
            client = await self.get_redis_client()
            result = client.delete(key)
            logger.debug(f"Cache delete for key: {key}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {str(e)}")
            return False
    
    async def get_vendor_availability(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Get cached vendor availability data."""
        key = self._get_cache_key("vendor_availability", vendor_id)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_vendor_availability(self, vendor_id: str, availability_data: Dict[str, Any]) -> bool:
        """Cache vendor availability data."""
        key = self._get_cache_key("vendor_availability", vendor_id)
        return await self.set(key, availability_data, self.default_ttl)
    
    async def invalidate_vendor_cache(self, vendor_id: str) -> bool:
        """Invalidate all cached data for a vendor."""
        keys_to_delete = [
            self._get_cache_key("vendor_availability", vendor_id),
            self._get_cache_key("vendor_catalog", vendor_id),
            self._get_cache_key("vendor_pricing", vendor_id)
        ]
        
        results = []
        for key in keys_to_delete:
            result = await self.delete(key)
            results.append(result)
        
        return all(results)
    
    async def get_catalog_data(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached catalog data."""
        key = self._get_cache_key("catalog", cache_key)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_catalog_data(self, cache_key: str, catalog_data: Dict[str, Any]) -> bool:
        """Cache catalog data."""
        key = self._get_cache_key("catalog", cache_key)
        return await self.set(key, catalog_data, self.price_cache_ttl)
    
    async def get_pricing_data(self, pricing_key: str) -> Optional[Dict[str, Any]]:
        """Get cached pricing data."""
        key = self._get_cache_key("pricing", pricing_key)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_pricing_data(self, pricing_key: str, pricing_data: Dict[str, Any]) -> bool:
        """Cache pricing data."""
        key = self._get_cache_key("pricing", pricing_key)
        return await self.set(key, pricing_data, self.price_cache_ttl)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health."""
        try:
            client = await self.get_redis_client()
            start_time = datetime.utcnow()
            client.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "healthy",
                "response_time_ms": round(response_time * 1000, 2),
                "connected": True
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "connected": False
            }


# Global cache service instance
cache_service = CacheService()
