from pydantic_settings import BaseSettings
from typing import Optional
import os
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/oxygen_platform")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Message Broker
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    RABBITMQ_REQUIRED: bool = os.getenv("RABBITMQ_REQUIRED", "false").lower() == "true"
    
    # Service URLs
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    ORDER_SERVICE_URL: str = os.getenv("ORDER_SERVICE_URL", "http://localhost:8005")
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8004")
    PAYMENT_SERVICE_URL: str = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8008")
    REVIEW_SERVICE_URL: str = os.getenv("REVIEW_SERVICE_URL", "http://localhost:8009")
    NOTIFICATION_SERVICE_URL: str = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010")
    LOCATION_SERVICE_URL: str = os.getenv("LOCATION_SERVICE_URL", "http://localhost:8003")
    PRICING_SERVICE_URL: str = os.getenv("PRICING_SERVICE_URL", "http://localhost:8006")
    SUPPLIER_ONBOARDING_SERVICE_URL: str = os.getenv("SUPPLIER_ONBOARDING_SERVICE_URL", "http://localhost:8002")
    
    # Admin Service Specific
    ADMIN_SERVICE_PORT: int = int(os.getenv("ADMIN_SERVICE_PORT", "8011"))
    
    # Admin Configuration
    ADMIN_SESSION_TIMEOUT_HOURS: int = int(os.getenv("ADMIN_SESSION_TIMEOUT_HOURS", "8"))
    MAX_EXPORT_RECORDS: int = int(os.getenv("MAX_EXPORT_RECORDS", "10000"))
    ANALYTICS_CACHE_TTL_MINUTES: int = int(os.getenv("ANALYTICS_CACHE_TTL_MINUTES", "15"))
    
    # Monitoring Configuration
    HEALTH_CHECK_TIMEOUT_SECONDS: int = int(os.getenv("HEALTH_CHECK_TIMEOUT_SECONDS", "5"))
    METRICS_RETENTION_DAYS: int = int(os.getenv("METRICS_RETENTION_DAYS", "30"))
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-admin-key-here")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
