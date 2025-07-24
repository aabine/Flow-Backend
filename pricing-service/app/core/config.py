from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # Service Configuration
    VERSION: str = Field("1.0.0", env="PRICING_SERVICE_VERSION")
    SERVICE_NAME: str = Field("pricing-service", env="SERVICE_NAME")
    DEBUG: bool = Field(False, env="DEBUG")

    # Database Configuration
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_ECHO: bool = Field(False, env="DATABASE_ECHO")
    DATABASE_SCHEMA: str = Field("pricing", env="DATABASE_SCHEMA")
    POOL_SIZE: int = Field(5, env="POOL_SIZE")
    MAX_OVERFLOW: int = Field(10, env="MAX_OVERFLOW")

    # Redis Configuration
    REDIS_URL: str = Field("redis://localhost:6379", env="REDIS_URL")

    # RabbitMQ Configuration
    RABBITMQ_URL: str = Field("amqp://guest:guest@localhost:5672/", env="RABBITMQ_URL")

    # External Service URLs
    USER_SERVICE_URL: str = Field("http://localhost:8001", env="USER_SERVICE_URL")
    INVENTORY_SERVICE_URL: str = Field("http://localhost:8004", env="INVENTORY_SERVICE_URL")
    ORDER_SERVICE_URL: str = Field("http://localhost:8003", env="ORDER_SERVICE_URL")
    LOCATION_SERVICE_URL: str = Field("http://localhost:8005", env="LOCATION_SERVICE_URL")
    WEBSOCKET_SERVICE_URL: str = Field("http://localhost:8012", env="WEBSOCKET_SERVICE_URL")

    # Bidding Configuration
    DEFAULT_AUCTION_DURATION_HOURS: int = Field(24, env="DEFAULT_AUCTION_DURATION_HOURS")
    MIN_AUCTION_DURATION_HOURS: int = Field(1, env="MIN_AUCTION_DURATION_HOURS")
    MAX_AUCTION_DURATION_HOURS: int = Field(168, env="MAX_AUCTION_DURATION_HOURS")  # 1 week
    DEFAULT_QUOTE_EXPIRY_HOURS: int = Field(48, env="DEFAULT_QUOTE_EXPIRY_HOURS")
    MIN_BID_INCREMENT: float = Field(0.01, env="MIN_BID_INCREMENT")
    MAX_DELIVERY_DISTANCE_KM: float = Field(100.0, env="MAX_DELIVERY_DISTANCE_KM")

    # Vendor Selection Algorithm Weights
    PRICE_WEIGHT: float = Field(0.4, env="PRICE_WEIGHT")
    RATING_WEIGHT: float = Field(0.3, env="RATING_WEIGHT")
    DISTANCE_WEIGHT: float = Field(0.2, env="DISTANCE_WEIGHT")
    DELIVERY_TIME_WEIGHT: float = Field(0.1, env="DELIVERY_TIME_WEIGHT")

    # Performance Thresholds
    MIN_VENDOR_RATING: float = Field(3.0, env="MIN_VENDOR_RATING")
    MAX_DELIVERY_TIME_HOURS: int = Field(48, env="MAX_DELIVERY_TIME_HOURS")

    # Notification Settings
    ENABLE_REAL_TIME_NOTIFICATIONS: bool = Field(True, env="ENABLE_REAL_TIME_NOTIFICATIONS")
    ENABLE_EMAIL_NOTIFICATIONS: bool = Field(True, env="ENABLE_EMAIL_NOTIFICATIONS")

    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(60, env="RATE_LIMIT_PER_MINUTE")

    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # CORS
    ALLOWED_ORIGINS: List[str] = Field(["*"], env="ALLOWED_ORIGINS")

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()