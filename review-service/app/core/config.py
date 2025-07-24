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
    
    # Service URLs
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    ORDER_SERVICE_URL: str = os.getenv("ORDER_SERVICE_URL", "http://localhost:8005")
    NOTIFICATION_SERVICE_URL: str = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8010")
    
    # Review Service Specific
    REVIEW_SERVICE_PORT: int = int(os.getenv("REVIEW_SERVICE_PORT", "8009"))
    
    # Review Configuration
    MAX_REVIEW_LENGTH: int = int(os.getenv("MAX_REVIEW_LENGTH", "1000"))
    REVIEW_EDIT_WINDOW_HOURS: int = int(os.getenv("REVIEW_EDIT_WINDOW_HOURS", "24"))
    MIN_RATING: int = int(os.getenv("MIN_RATING", "1"))
    MAX_RATING: int = int(os.getenv("MAX_RATING", "5"))
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
