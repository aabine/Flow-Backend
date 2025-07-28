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

    # Security Configuration
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    MFA_ISSUER: str = os.getenv("MFA_ISSUER", "Oxygen Supply Platform")

    # Database Security
    DB_SSL_MODE: str = os.getenv("DB_SSL_MODE", "prefer")
    DB_AUDIT_LOGGING: bool = os.getenv("DB_AUDIT_LOGGING", "false").lower() == "true"

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
