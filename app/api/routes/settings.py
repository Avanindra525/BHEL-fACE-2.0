"""Settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.dependencies import get_current_user

router = APIRouter()


@router.get("")
def get_settings(current_user=Depends(get_current_user)) -> dict[str, object]:
    """Return application settings exposed to the UI."""

    return {
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "app_version": "1.0.0",
        "face_detection_model": settings.face_detection_model,
        "face_similarity_threshold": settings.face_similarity_threshold,
        "max_failed_login_attempts": settings.max_failed_login_attempts,
        "lockout_minutes": settings.lockout_minutes,
        "jwt_access_token_expire_minutes": settings.jwt_access_token_expire_minutes,
        "jwt_refresh_token_expire_days": settings.jwt_refresh_token_expire_days,
    }
