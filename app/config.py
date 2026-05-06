"""
Application configuration and settings
"""

import os
from typing import ClassVar

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file (override=True so .env wins over stale shell exports)
load_dotenv(override=True)


# OpenAI client configuration
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Application settings
class Config:
    """Application configuration settings"""

    # Environment setting
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # OpenAI settings
    OPENAI_MODEL = "gpt-4o"

    # File upload settings
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".zip"}

    # Progress tracking settings
    MAX_SSE_ITERATIONS = 300  # 5 minutes max (300 seconds)
    PROGRESS_UPDATE_INTERVAL = 1  # seconds

    # Session settings
    SESSION_TIMEOUT = 3600  # 1 hour in seconds

    # Database settings
    _db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://localhost/dependiq")
    # Convert postgres:// to postgresql+asyncpg:// for async support
    # Render and other platforms often provide postgres:// or postgresql://
    if _db_url.startswith("postgres://"):
        DATABASE_URL = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _db_url.startswith("postgresql://"):
        DATABASE_URL = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = _db_url

    # JWT settings
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Application URL
    APP_URL = os.getenv("APP_URL", "http://localhost:8000")

    # GitHub OAuth settings
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    GITHUB_REDIRECT_URI = os.getenv(
        "GITHUB_REDIRECT_URI", "http://localhost:8000/api/auth/github/callback"
    )

    # Session security
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    SESSION_SECRET = os.getenv(
        "SESSION_SECRET", "dev-session-secret-change-in-production"
    )
    SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"

    # GitHub API settings
    GITHUB_API_BASE = "https://api.github.com"
    GITHUB_OAUTH_SCOPES = "repo,user:email"  # Access to repos and email

    # Email settings (optional - for verification/reset emails)
    EMAIL_SERVICE = os.getenv("EMAIL_SERVICE", "gmail")  # gmail or sendgrid
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    GMAIL_USER = os.getenv("GMAIL_USER")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@example.com")
    EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "dependiq")

    # File processing settings
    MAX_ANALYZABLE_FILES = 20
    MAX_PRIORITY_FILES = 15
    MAX_STRUCTURE_SUMMARY = 50
    MAX_DIRECTORIES = 30

    # Temporary file settings
    TEMP_DIR = "/tmp"

    @classmethod
    def get_temp_file_path(cls, session_id: str, suffix: str = ".zip") -> str:
        """Generate a temporary file path for a session"""
        return f"{cls.TEMP_DIR}/analyze_{session_id}{suffix}"

    @classmethod
    def get_temp_data_path(cls, session_id: str) -> str:
        """Generate a temporary data file path for a session"""
        return f"{cls.TEMP_DIR}/{session_id}.json"
