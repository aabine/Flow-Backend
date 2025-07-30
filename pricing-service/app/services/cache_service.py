"""
Redis Caching Service for Pricing Service
Provides caching for pricing data, vendor catalogs, and price comparisons
"""

import json
import redis
import asyncio
from typing import Optional, Dict, Any, Union, List
from datetime import datetime, timedelta
import logging
import os
import hashlib

logger = logging.getLogger(__name__)


class PricingCacheService:
    """Redis-based caching service for Pricing Service."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/3")  # Use DB 3 for pricing cache
        self.default_ttl = int(os.getenv("PRICING_CACHE_TTL_SECONDS", "1800"))  # 30 minutes
        self.vendor_cache_ttl = int(os.getenv("VENDOR_CACHE_TTL_SECONDS", "3600"))  # 1 hour
        self.price_comparison_ttl = int(os.getenv("PRICE_COMPARISON_TTL_SECONDS", "300"))  # 5 minutes
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
                        logger.info("Pricing Service Redis connection established successfully")
                    except Exception as e:
                        logger.error(f"Failed to connect to Redis: {str(e)}")
                        self._redis_client = None
                        raise
        return self._redis_client
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        """Generate standardized cache key."""
        return f"pricing:{prefix}:{identifier}"
    
    def _generate_cache_key_from_params(self, prefix: str, **params) -> str:
        """Generate cache key from parameters."""
        # Sort parameters for consistent key generation
        sorted_params = sorted(params.items())
        param_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        param_hash = hashlib.md5(param_string.encode()).hexdigest()
        return f"pricing:{prefix}:{param_hash}"
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached data by key."""
        try:
            client = await self.get_redis_client()
            cached_data = client.get(key)
            
            if cached_data:
                data = json.loads(cached_data)
                logger.debug(f"Pricing cache hit for key: {key}")
                return data
            else:
                logger.debug(f"Pricing cache miss for key: {key}")
                return None
                
        except Exception as e:
            logger.error(f"Pricing cache get error for key {key}: {str(e)}")
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
            logger.debug(f"Pricing cache set for key: {key}, TTL: {ttl}s")
            return result
            
        except Exception as e:
            logger.error(f"Pricing cache set error for key {key}: {str(e)}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        try:
            client = await self.get_redis_client()
            result = client.delete(key)
            logger.debug(f"Pricing cache delete for key: {key}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Pricing cache delete error for key {key}: {str(e)}")
            return False
    
    # Pricing-specific caching methods
    
    async def get_vendor_pricing(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Get cached vendor pricing data."""
        key = self._get_cache_key("vendor_pricing", vendor_id)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_vendor_pricing(self, vendor_id: str, pricing_data: Dict[str, Any]) -> bool:
        """Cache vendor pricing data."""
        key = self._get_cache_key("vendor_pricing", vendor_id)
        return await self.set(key, pricing_data, self.vendor_cache_ttl)
    
    async def get_product_pricing(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get cached product pricing data."""
        key = self._get_cache_key("product_pricing", product_id)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_product_pricing(self, product_id: str, pricing_data: Dict[str, Any]) -> bool:
        """Cache product pricing data."""
        key = self._get_cache_key("product_pricing", product_id)
        return await self.set(key, pricing_data, self.default_ttl)
    
    async def get_price_comparison(self, **params) -> Optional[Dict[str, Any]]:
        """Get cached price comparison data."""
        key = self._generate_cache_key_from_params("price_comparison", **params)
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_price_comparison(self, comparison_data: Dict[str, Any], **params) -> bool:
        """Cache price comparison data."""
        key = self._generate_cache_key_from_params("price_comparison", **params)
        return await self.set(key, comparison_data, self.price_comparison_ttl)
    
    async def get_vendor_catalog(self, vendor_id: str, filters: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Get cached vendor catalog data."""
        if filters:
            key = self._generate_cache_key_from_params("vendor_catalog", vendor_id=vendor_id, **filters)
        else:
            key = self._get_cache_key("vendor_catalog", vendor_id)
        
        cached_result = await self.get(key)
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_vendor_catalog(self, vendor_id: str, catalog_data: Dict[str, Any], filters: Dict[str, Any] = None) -> bool:
        """Cache vendor catalog data."""
        if filters:
            key = self._generate_cache_key_from_params("vendor_catalog", vendor_id=vendor_id, **filters)
        else:
            key = self._get_cache_key("vendor_catalog", vendor_id)
        
        return await self.set(key, catalog_data, self.vendor_cache_ttl)
    
    async def get_nearby_vendors(self, latitude: float, longitude: float, radius_km: float) -> Optional[Dict[str, Any]]:
        """Get cached nearby vendors data."""
        key = self._generate_cache_key_from_params(
            "nearby_vendors",
            lat=round(latitude, 4),  # Round to reduce cache key variations
            lng=round(longitude, 4),
            radius=radius_km
        )
        cached_result = await self.get(key)
        
        if cached_result:
            return cached_result.get("data")
        return None
    
    async def set_nearby_vendors(self, latitude: float, longitude: float, radius_km: float, vendors_data: Dict[str, Any]) -> bool:
        """Cache nearby vendors data."""
        key = self._generate_cache_key_from_params(
            "nearby_vendors",
            lat=round(latitude, 4),
            lng=round(longitude, 4),
            radius=radius_km
        )
        return await self.set(key, vendors_data, self.vendor_cache_ttl)
    
    async def invalidate_vendor_cache(self, vendor_id: str) -> bool:
        """Invalidate all cached data for a vendor."""
        try:
            client = await self.get_redis_client()
            
            # Get all keys related to this vendor
            patterns = [
                f"pricing:vendor_pricing:{vendor_id}",
                f"pricing:vendor_catalog:{vendor_id}*",
                f"pricing:price_comparison:*vendor_id={vendor_id}*"
            ]
            
            keys_to_delete = []
            for pattern in patterns:
                keys = client.keys(pattern)
                keys_to_delete.extend(keys)
            
            if keys_to_delete:
                result = client.delete(*keys_to_delete)
                logger.info(f"Invalidated {result} cache keys for vendor {vendor_id}")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating vendor cache for {vendor_id}: {str(e)}")
            return False
    
    async def invalidate_product_cache(self, product_id: str) -> bool:
        """Invalidate all cached data for a product."""
        try:
            client = await self.get_redis_client()
            
            # Get all keys related to this product
            patterns = [
                f"pricing:product_pricing:{product_id}",
                f"pricing:price_comparison:*product_id={product_id}*"
            ]
            
            keys_to_delete = []
            for pattern in patterns:
                keys = client.keys(pattern)
                keys_to_delete.extend(keys)
            
            if keys_to_delete:
                result = client.delete(*keys_to_delete)
                logger.info(f"Invalidated {result} cache keys for product {product_id}")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating product cache for {product_id}: {str(e)}")
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            client = await self.get_redis_client()
            
            # Get all pricing cache keys
            all_keys = client.keys("pricing:*")
            
            stats = {
                "total_keys": len(all_keys),
                "vendor_pricing_keys": len(client.keys("pricing:vendor_pricing:*")),
                "product_pricing_keys": len(client.keys("pricing:product_pricing:*")),
                "price_comparison_keys": len(client.keys("pricing:price_comparison:*")),
                "vendor_catalog_keys": len(client.keys("pricing:vendor_catalog:*")),
                "nearby_vendors_keys": len(client.keys("pricing:nearby_vendors:*"))
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return {"error": str(e)}
    
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
pricing_cache_service = PricingCacheService()
