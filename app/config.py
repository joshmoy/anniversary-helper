"""
Configuration settings for the Church Anniversary & Birthday Helper app.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AI/LLM Configuration
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")

    # Supabase Database Configuration
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_key: str = Field(..., env="SUPABASE_KEY")
    supabase_service_key: Optional[str] = Field(None, env="SUPABASE_SERVICE_KEY")

    # Twilio WhatsApp Configuration
    twilio_account_sid: str = Field(..., env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(..., env="TWILIO_AUTH_TOKEN")
    whatsapp_from: str = Field(..., env="WHATSAPP_FROM")
    whatsapp_to: str = Field(..., env="WHATSAPP_TO")

    # Application Configuration
    schedule_time: str = Field("06:00", env="SCHEDULE_TIME")
    timezone: str = Field("Europe/London", env="TIMEZONE")
    csv_upload_path: str = Field("./data/", env="CSV_UPLOAD_PATH")

    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    backup_enabled: bool = Field(True, env="BACKUP_ENABLED")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
