"""
Application configuration and settings
"""

import os
from typing import ClassVar

from dotenv import load_dotenv

# Load environment variables from .env file (override=True so .env wins over stale shell exports)
load_dotenv(override=True)


# Application settings
class Config:
    """Application configuration settings"""

    # Environment setting
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

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

    # WorkOS AuthKit settings
    WORKOS_API_KEY = os.getenv("WORKOS_API_KEY", "")
    WORKOS_CLIENT_ID = os.getenv("WORKOS_CLIENT_ID", "")
    WORKOS_REDIRECT_URI = os.getenv(
        "WORKOS_REDIRECT_URI", "http://localhost:8000/api/auth/callback"
    )

    # Application URL
    APP_URL = os.getenv("APP_URL", "http://localhost:8000")

    # Session security
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    SECURE_COOKIES = os.getenv("SECURE_COOKIES", "false").lower() == "true"

    # GitHub API settings
    GITHUB_API_BASE = "https://api.github.com"

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
