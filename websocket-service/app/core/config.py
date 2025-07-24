from pydantic_settings import BaseSettings
import os
from functools import lru_cache


class Settings(BaseSettings):
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-here")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    
    # Service URLs
    USER_SERVICE_URL: str = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
    
    # WebSocket Settings
    WEBSOCKET_PING_INTERVAL: int = int(os.getenv("WEBSOCKET_PING_INTERVAL", "30"))
    WEBSOCKET_MAX_IDLE_MINUTES: int = int(os.getenv("WEBSOCKET_MAX_IDLE_MINUTES", "30"))
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
