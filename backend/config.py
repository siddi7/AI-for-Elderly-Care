# Configuration Settings for Elderly Care AI System

import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application Settings
    app_name: str = "Elderly Care AI System"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, env="DEBUG")

    # Server Settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")

    # Database Settings
    database_url: str = Field(
        default="postgresql://elderly_care:password@localhost:5432/elderly_care_db",
        env="DATABASE_URL"
    )

    # Redis Settings
    redis_url: str = Field(
        default="redis://localhost:6379",
        env="REDIS_URL"
    )

    # JWT Settings
    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        env="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24

    # API Keys
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    twilio_account_sid: Optional[str] = Field(default=None, env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(default=None, env="TWILIO_PHONE_NUMBER")
    sendgrid_api_key: Optional[str] = Field(default=None, env="SENDGRID_API_KEY")
    telegram_bot_token: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")

    # Agent Settings
    health_agent_enabled: bool = True
    safety_agent_enabled: bool = True
    reminder_agent_enabled: bool = True

    # Health Monitoring Thresholds
    heart_rate_min: int = 60
    heart_rate_max: int = 100
    blood_pressure_systolic_min: int = 90
    blood_pressure_systolic_max: int = 140
    blood_pressure_diastolic_min: int = 60
    blood_pressure_diastolic_max: int = 90
    glucose_min: int = 70
    glucose_max: int = 140
    oxygen_saturation_min: int = 95

    # Safety Monitoring Settings
    fall_detection_sensitivity: float = 0.8
    inactivity_threshold_minutes: int = 30
    movement_check_interval_seconds: int = 300

    # Reminder Settings
    reminder_retry_attempts: int = 3
    reminder_escalation_minutes: int = 15
    voice_reminder_enabled: bool = True

    # Alert Settings
    alert_retry_attempts: int = 3
    alert_escalation_minutes: int = 10
    emergency_contacts_required: int = 2

    # CORS Settings
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        env="CORS_ORIGINS"
    )

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # ML Model Settings
    ml_model_path: str = Field(default="./models", env="ML_MODEL_PATH")
    prediction_enabled: bool = True

    # File Upload Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    allowed_extensions: List[str] = [".csv", ".json", ".txt"]

    # Security Settings
    bcrypt_rounds: int = 12
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

# Environment-specific configurations
def get_settings() -> Settings:
    """Get settings instance with validation"""
    return settings

def validate_settings() -> bool:
    """Validate critical settings are configured"""
    required_settings = [
        settings.database_url,
        settings.redis_url,
        settings.jwt_secret_key
    ]

    missing_settings = [setting for setting in required_settings if not setting]

    if missing_settings:
        print(f"Missing required settings: {missing_settings}")
        return False

    return True
