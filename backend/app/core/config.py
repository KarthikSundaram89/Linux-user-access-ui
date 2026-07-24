"""
Application Configuration Module.
All configurable values are managed through environment variables or the admin UI.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    # Application
    APP_NAME: str = "Enterprise Linux Access Portal"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-in-production-use-openssl-rand-hex-32"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/portal.db"
    DATABASE_ECHO: bool = False

    # Azure AD / Microsoft Entra ID (for SSO only - no Graph API)
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"
    AZURE_AUTHORITY: str = ""
    AZURE_SCOPES: str = "User.Read"

    # AD Export File (daily export from Active Directory to shared folder)
    AD_EXPORT_PATH: str = "/shared/ad_exports"
    AD_EXPORT_ENCODING: str = "utf-8"

    # EC2 Inventory File (daily EC2 export with account, region, tags)
    EC2_INVENTORY_PATH: str = "/shared/ec2_inventory"
    EC2_INVENTORY_ENCODING: str = "utf-8"

    # AWS Configuration (for live EC2 status checks)
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_PROFILE_MAPPING: str = ""  # JSON: {"account_name": "aws_profile_name"}

    # SMTP Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@company.com"
    SMTP_FROM_NAME: str = "Linux Access Portal"
    SMTP_USE_TLS: bool = True

    # SSH Provisioning
    SSH_TIMEOUT: int = 30
    SSH_RETRIES: int = 3
    SSH_RETRY_DELAY: int = 5
    SSH_CONCURRENT_LIMIT: int = 10
    SSH_KEY_PATH: str = "./data/ssh_keys"

    # Sudo Configuration
    SUDO_VALIDITY_DAYS: int = 90
    SUDO_REMINDER_DAYS: int = 15
    SUDO_EXPIRY_CHECK_INTERVAL_HOURS: int = 24

    # Session
    SESSION_TIMEOUT_MINUTES: int = 60
    SESSION_SECRET_KEY: str = "session-secret-change-in-production"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # File Paths
    DATA_DIR: str = "./data"
    LOG_DIR: str = "./logs"
    UPLOAD_DIR: str = "./data/uploads"

    # Emergency Admin
    EMERGENCY_ADMIN_USERNAME: str = "admin"
    EMERGENCY_ADMIN_PASSWORD: str = "change-this-immediately"

    @property
    def azure_authority_url(self) -> str:
        if self.AZURE_AUTHORITY:
            return self.AZURE_AUTHORITY
        return f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def aws_profile_map(self) -> dict:
        """Parse AWS_PROFILE_MAPPING JSON string into a dict."""
        import json
        if not self.AWS_PROFILE_MAPPING:
            return {}
        try:
            return json.loads(self.AWS_PROFILE_MAPPING)
        except (json.JSONDecodeError, TypeError):
            return {}

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
