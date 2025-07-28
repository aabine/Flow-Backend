import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Basic service configuration
    SERVICE_NAME: str = "pricing-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("PORT", "8006"))
    
    # Database configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://user:password@localhost:5432/oxygen_platform"
    )
    
    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Security configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "pricing-service-secret-key")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "jwt-secret-key")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    
    # CORS configuration
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    
    # External service URLs
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8004")
    LOCATION_SERVICE_URL: str = os.getenv("LOCATION_SERVICE_URL", "http://localhost:8003")
    ORDER_SERVICE_URL: str = os.getenv("ORDER_SERVICE_URL", "http://localhost:8005")
    NOTIFICATION_SERVICE_URL: str = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010")
    
    # Message broker configuration
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    
    # Pricing service specific configuration
    DEFAULT_SEARCH_RADIUS_KM: float = float(os.getenv("DEFAULT_SEARCH_RADIUS_KM", "50.0"))
    MAX_SEARCH_RADIUS_KM: float = float(os.getenv("MAX_SEARCH_RADIUS_KM", "200.0"))
    PRICE_CACHE_TTL_SECONDS: int = int(os.getenv("PRICE_CACHE_TTL_SECONDS", "300"))  # 5 minutes
    VENDOR_CACHE_TTL_SECONDS: int = int(os.getenv("VENDOR_CACHE_TTL_SECONDS", "1800"))  # 30 minutes
    
    # Pagination defaults
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", "20"))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", "100"))
    
    # Rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100"))
    
    # Logging configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT", 
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Performance settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    
    # Feature flags
    ENABLE_PRICE_ALERTS: bool = os.getenv("ENABLE_PRICE_ALERTS", "true").lower() == "true"
    ENABLE_VENDOR_RECOMMENDATIONS: bool = os.getenv("ENABLE_VENDOR_RECOMMENDATIONS", "true").lower() == "true"
    ENABLE_BULK_PRICING: bool = os.getenv("ENABLE_BULK_PRICING", "true").lower() == "true"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
