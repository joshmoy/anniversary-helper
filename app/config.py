"""
Configuration settings for the Church Anniversary & Birthday Helper app.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AI/LLM Configuration
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")

    # Supabase Database Configuration
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_key: str = Field(..., env="SUPABASE_KEY")
    supabase_service_key: Optional[str] = Field(None, env="SUPABASE_SERVICE_KEY")
    
    # Supabase Storage Configuration
    supabase_storage_bucket: str = Field("csv-uploads", env="SUPABASE_STORAGE_BUCKET")

    # Twilio WhatsApp Configuration
    twilio_account_sid: str = Field(..., env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(..., env="TWILIO_AUTH_TOKEN")
    whatsapp_from: str = Field(..., env="WHATSAPP_FROM")
    whatsapp_to: str = Field(..., env="WHATSAPP_TO")

    # Application Configuration
    schedule_time: str = Field("06:00", env="SCHEDULE_TIME")
    timezone: str = Field("Europe/London", env="TIMEZONE")

    # Authentication Configuration
    jwt_secret_key: str = Field("your-super-secret-jwt-key-change-in-production", env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(1440, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")  # 24 hours
    
    cron_secret: str = Field("your-super-secret", env="CRON_SECRET")
    job_url: str = Field("job-url", env="JOB_URL")
    frontend_url: str = Field("http://localhost:3000", env="CLIENT_URL")

    # Rate Limiting Configuration
    rate_limit_max_requests: int = Field(3, env="RATE_LIMIT_MAX_REQUESTS")
    rate_limit_window_hours: int = Field(3, env="RATE_LIMIT_WINDOW_HOURS")

    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    backup_enabled: bool = Field(True, env="BACKUP_ENABLED")

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables
    )


# Global settings instance
settings = Settings()
