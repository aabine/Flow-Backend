from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import List
import os


class Settings(BaseSettings):
    # Service Configuration
    SERVICE_NAME: str = Field("delivery-service", env="SERVICE_NAME")
    VERSION: str = Field("1.0.0", env="DELIVERY_SERVICE_VERSION")
    DEBUG: bool = Field(False, env="DEBUG")
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")

    # Database Configuration
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_ECHO: bool = Field(False, env="DATABASE_ECHO")
    DATABASE_SCHEMA: str = Field("delivery", env="DATABASE_SCHEMA")
    POOL_SIZE: int = Field(5, env="POOL_SIZE")
    MAX_OVERFLOW: int = Field(10, env="MAX_OVERFLOW")

    # Redis Configuration
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")

    # RabbitMQ Configuration
    RABBITMQ_URL: str = Field("amqp://guest:guest@localhost:5672/", env="RABBITMQ_URL")

    # External Service URLs
    USER_SERVICE_URL: str = Field("http://localhost:8001", env="USER_SERVICE_URL")
    ORDER_SERVICE_URL: str = Field("http://localhost:8005", env="ORDER_SERVICE_URL")
    LOCATION_SERVICE_URL: str = Field("http://localhost:8003", env="LOCATION_SERVICE_URL")
    NOTIFICATION_SERVICE_URL: str = Field("http://localhost:8010", env="NOTIFICATION_SERVICE_URL")
    WEBSOCKET_SERVICE_URL: str = Field("http://localhost:8012", env="WEBSOCKET_SERVICE_URL")
    INVENTORY_SERVICE_URL: str = Field("http://localhost:8004", env="INVENTORY_SERVICE_URL")

    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = Field("HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Delivery Configuration
    DEFAULT_DELIVERY_RADIUS_KM: float = Field(50.0, env="DEFAULT_DELIVERY_RADIUS_KM")
    MAX_DELIVERY_DISTANCE_KM: float = Field(100.0, env="MAX_DELIVERY_DISTANCE_KM")
    AVERAGE_SPEED_KMH: float = Field(40.0, env="AVERAGE_SPEED_KMH")
    DELIVERY_BUFFER_MINUTES: int = Field(15, env="DELIVERY_BUFFER_MINUTES")
    MAX_DELIVERIES_PER_ROUTE: int = Field(10, env="MAX_DELIVERIES_PER_ROUTE")

    # Driver Configuration
    MIN_DRIVER_RATING: float = Field(3.0, env="MIN_DRIVER_RATING")
    MAX_WORKING_HOURS: int = Field(12, env="MAX_WORKING_HOURS")
    BREAK_DURATION_MINUTES: int = Field(30, env="BREAK_DURATION_MINUTES")

    # Pricing Configuration
    BASE_DELIVERY_FEE: float = Field(5.0, env="BASE_DELIVERY_FEE")
    PRICE_PER_KM: float = Field(1.5, env="PRICE_PER_KM")
    URGENT_DELIVERY_MULTIPLIER: float = Field(2.0, env="URGENT_DELIVERY_MULTIPLIER")
    HIGH_PRIORITY_MULTIPLIER: float = Field(1.5, env="HIGH_PRIORITY_MULTIPLIER")

    # Route Optimization
    ENABLE_ROUTE_OPTIMIZATION: bool = Field(True, env="ENABLE_ROUTE_OPTIMIZATION")
    OPTIMIZATION_ALGORITHM: str = Field("nearest_neighbor", env="OPTIMIZATION_ALGORITHM")
    MAX_OPTIMIZATION_TIME_SECONDS: int = Field(30, env="MAX_OPTIMIZATION_TIME_SECONDS")

    # Real-time Tracking
    TRACKING_UPDATE_INTERVAL_SECONDS: int = Field(30, env="TRACKING_UPDATE_INTERVAL_SECONDS")
    ENABLE_REAL_TIME_TRACKING: bool = Field(True, env="ENABLE_REAL_TIME_TRACKING")
    GPS_ACCURACY_THRESHOLD_METERS: float = Field(100.0, env="GPS_ACCURACY_THRESHOLD_METERS")

    # Notifications
    ENABLE_SMS_NOTIFICATIONS: bool = Field(True, env="ENABLE_SMS_NOTIFICATIONS")
    ENABLE_EMAIL_NOTIFICATIONS: bool = Field(True, env="ENABLE_EMAIL_NOTIFICATIONS")
    ENABLE_PUSH_NOTIFICATIONS: bool = Field(True, env="ENABLE_PUSH_NOTIFICATIONS")

    # External APIs
    GOOGLE_MAPS_API_KEY: str = Field("", env="GOOGLE_MAPS_API_KEY")
    MAPBOX_ACCESS_TOKEN: str = Field("", env="MAPBOX_ACCESS_TOKEN")

    # File Storage
    UPLOAD_DIR: str = Field("uploads", env="UPLOAD_DIR")
    MAX_FILE_SIZE_MB: int = Field(10, env="MAX_FILE_SIZE_MB")
    ALLOWED_IMAGE_EXTENSIONS: List[str] = Field([".jpg", ".jpeg", ".png"], env="ALLOWED_IMAGE_EXTENSIONS")

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(60, env="RATE_LIMIT_PER_MINUTE")

    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    # CORS
    ALLOWED_ORIGINS: List[str] = Field(["*"], env="ALLOWED_ORIGINS")

    # Health Check
    HEALTH_CHECK_TIMEOUT_SECONDS: int = Field(30, env="HEALTH_CHECK_TIMEOUT_SECONDS")

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
