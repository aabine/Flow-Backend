from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/onboarding_db")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    class Config:
        env_file = ".env"

settings = Settings() 