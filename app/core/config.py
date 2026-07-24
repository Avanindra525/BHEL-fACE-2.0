"""Application settings loaded from environment variables.

Enterprise-level security settings for FaceAuth Enterprise.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings with enterprise security defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Application ──
    app_name: str = "FaceAuth Enterprise"
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = Field(default="faceauth-enterprise-local-development-secret-123", min_length=32)
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ── JWT ──
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 14
    jwt_algorithm: str = "HS256"

    # ── Oracle Database ──
    database_url: str = "oracle+oracledb://faceauth:FaceAuth123@localhost:1521?service_name=orcl"
    oracle_user: str = "faceauth"
    oracle_password: str = "FaceAuth123"
    oracle_dsn: str = "localhost:1521/orcl"
    oracle_schema: str = "faceauth"

    # ── Face Recognition ──
    face_detection_model: str = "SCRFD"
    insightface_model_name: str = "buffalo_l"
    face_similarity_threshold: float = 0.45

    # ── Password & Account Security ──
    max_failed_login_attempts: int = 5
    lockout_minutes: int = 15
    password_min_length: int = 12
    password_min_uppercase: int = 1
    password_min_lowercase: int = 1
    password_min_digits: int = 1
    password_min_special: int = 1
    password_history_count: int = 5  # Number of previous passwords to block
    password_expiry_days: int = 90  # Force password change after N days

    # ── Session & Timeout ──
    session_timeout_minutes: int = 60  # Idle session timeout
    remember_me_days: int = 30  # "Remember Me" extends refresh token validity

    # ── Rate Limiting ──
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 30  # General API
    rate_limit_login_requests_per_minute: int = 5  # Login-specific
    rate_limit_face_requests_per_minute: int = 10  # Face API

    # ── HTTP Security ──
    csrf_protection_enabled: bool = True
    secure_cookies: bool = True  # Set Secure flag on cookies
    samesite_cookies: str = "Lax"  # Lax, Strict, or None

    # ── Upload ──
    upload_dir: Path = Path("app/static/uploads")
    log_level: str = "INFO"

    @field_validator("app_secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, value: str) -> str:
        if len(value.strip()) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters long")
        return value

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


settings = get_settings()

