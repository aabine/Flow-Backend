from pydantic_settings import BaseSettings
from typing import Optional
import os
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/oxygen_platform")
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-here")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # Inventory Service Specific
    INVENTORY_SERVICE_PORT: int = int(os.getenv("INVENTORY_SERVICE_PORT", "8004"))

    # Cylinder Management Configuration
    CYLINDER_ALLOCATION_RADIUS_KM: float = float(os.getenv("CYLINDER_ALLOCATION_RADIUS_KM", "50.0"))
    MAX_CYLINDER_ALLOCATION_RADIUS_KM: float = float(os.getenv("MAX_CYLINDER_ALLOCATION_RADIUS_KM", "200.0"))
    CYLINDER_MAINTENANCE_INTERVAL_DAYS: int = int(os.getenv("CYLINDER_MAINTENANCE_INTERVAL_DAYS", "365"))
    CYLINDER_PRESSURE_TEST_INTERVAL_DAYS: int = int(os.getenv("CYLINDER_PRESSURE_TEST_INTERVAL_DAYS", "1825"))
    MIN_CYLINDER_FILL_PERCENTAGE: float = float(os.getenv("MIN_CYLINDER_FILL_PERCENTAGE", "90.0"))
    EMERGENCY_CYLINDER_RESERVE_PERCENTAGE: float = float(os.getenv("EMERGENCY_CYLINDER_RESERVE_PERCENTAGE", "20.0"))

    # Quality Control Configuration
    QUALITY_CHECK_FREQUENCY_DAYS: int = int(os.getenv("QUALITY_CHECK_FREQUENCY_DAYS", "90"))
    QUALITY_CHECK_PASS_THRESHOLD: float = float(os.getenv("QUALITY_CHECK_PASS_THRESHOLD", "95.0"))

    # Pricing Integration
    PRICING_SERVICE_URL: str = os.getenv("PRICING_SERVICE_URL", "http://pricing-service:8006")
    PRICING_SERVICE_TIMEOUT: int = int(os.getenv("PRICING_SERVICE_TIMEOUT", "30"))

    # Event Publishing
    ENABLE_CYLINDER_EVENTS: bool = os.getenv("ENABLE_CYLINDER_EVENTS", "true").lower() == "true"
    EVENT_BATCH_SIZE: int = int(os.getenv("EVENT_BATCH_SIZE", "100"))

    # Allocation Algorithm Weights
    ALLOCATION_DISTANCE_WEIGHT: float = float(os.getenv("ALLOCATION_DISTANCE_WEIGHT", "0.4"))
    ALLOCATION_COST_WEIGHT: float = float(os.getenv("ALLOCATION_COST_WEIGHT", "0.3"))
    ALLOCATION_QUALITY_WEIGHT: float = float(os.getenv("ALLOCATION_QUALITY_WEIGHT", "0.2"))
    ALLOCATION_AVAILABILITY_WEIGHT: float = float(os.getenv("ALLOCATION_AVAILABILITY_WEIGHT", "0.1"))

    # Service URLs
    WEBSOCKET_SERVICE_URL: str = os.getenv("WEBSOCKET_SERVICE_URL", "http://localhost:8012")

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    RABBITMQ_REQUIRED: bool = os.getenv("RABBITMQ_REQUIRED", "false").lower() == "true"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
