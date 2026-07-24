"""Face registration and login API routes with full production pipeline.

Integrates with the FaceRecognizer orchestrator for:
  - Face Registration: quality validation → SCRFD detection → alignment → ArcFace embedding → Oracle storage
  - Face Login: detection → quality → liveness → alignment → embedding → gallery matching → JWT
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.core.security import create_access_token, create_refresh_token
from app.face_ai.recognizer import FaceRecognizer
from app.models.audit_log import AuditLog
from app.models.face_sample import FaceSample
from app.models.login_log import LoginLog
from app.models.user import User

router = APIRouter()


def get_recognizer() -> FaceRecognizer:
    """Return the singleton FaceRecognizer instance."""
    return FaceRecognizer()


def _decode_upload_to_array(file: UploadFile) -> np.ndarray | None:
    """Decode an uploaded image file to a BGR numpy array."""
    content = file.file.read()
    if not content:
        return None
    arr = np.frombuffer(content, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_face(
    file: UploadFile,
    pose: str = Form(default="front"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    recognizer: FaceRecognizer = Depends(get_recognizer),
) -> dict[str, object]:
    """Register a face sample with full production pipeline.

    Pipeline:
        1. Decode uploaded image
        2. Detect exactly one face (SCRFD)
        3. Validate quality (blur, brightness, contrast, face size, pose, eyes)
        4. Align face to canonical position
        5. Generate ArcFace embedding
        6. Save JPEG to uploads directory
        7. Store embedding + metadata in Oracle face_samples table
        8. Mark user as face_registered
        9. Write audit log
    """
    # Step 1: Decode image
    image = _decode_upload_to_array(file)
    if image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or empty image file")

    # Step 2-5: Run recognition pipeline
    result = recognizer.register_face(
        image=image,
        user_id=current_user.user_id,
        pose=pose,
        staff_number=current_user.staff_number,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Face registration failed"),
        )

    # Step 6: Store face sample in Oracle
    face_sample = FaceSample(
        user_id=current_user.user_id,
        pose=pose,
        image_path=result["image_path"],
        embedding_blob=result["embedding_bytes"],
        quality_score=int(result["quality_score"] * 100),
    )

    # Handle Oracle sequence for primary key
    try:
        next_id = db.execute(text("SELECT face_samples_seq.NEXTVAL FROM dual")).scalar_one()
        face_sample.face_sample_id = int(next_id)
    except Exception:
        pass  # Let auto-increment handle it

    db.add(face_sample)

    # Step 7: Mark user as face registered
    if current_user.face_registered != "Y":
        current_user.face_registered = "Y"
        current_user.profile_completed = "Y"
        current_user.updated_at = datetime.utcnow()

    # Step 8: Write audit log
    audit = AuditLog(
        user_id=current_user.user_id,
        action="face_registered",
        details=f"Face registered [{pose}] - quality: {result['quality_score']:.2f}",
    )
    db.add(audit)

    db.commit()
    db.refresh(current_user)

    logger.info(
        "face_sample_registered",
        extra={
            "user": current_user.username,
            "pose": pose,
            "quality_score": result["quality_score"],
            "face_size": result.get("face", {}).get("face_size"),
        },
    )

    return {
        "message": f"Face sample registered for pose: {pose}",
        "user": current_user.username,
        "quality_score": result["quality_score"],
        "face_size": result.get("face", {}).get("face_size"),
        "image_path": result["image_path"],
        "checks": {k: v.get("passed") for k, v in result.get("checks", {}).items()},
    }


@router.post("/register-multi-pose", status_code=status.HTTP_201_CREATED)
async def register_multi_pose(
    front: UploadFile,
    left: UploadFile | None = None,
    right: UploadFile | None = None,
    up: UploadFile | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    recognizer: FaceRecognizer = Depends(get_recognizer),
) -> dict[str, object]:
    """Register multiple face poses in a single request.

    Accepts up to 4 images (front, left, right, up) and processes each
    through the full pipeline, storing all successful captures.
    """
    images: dict[str, np.ndarray] = {}
    pose_map = {"front": front, "left": left, "right": right, "up": up}

    for pose_name, upload_file in pose_map.items():
        if upload_file:
            img = _decode_upload_to_array(upload_file)
            if img is not None:
                images[pose_name] = img

    if "front" not in images:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Front pose image is required")

    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for pose_name, img in images.items():
        result = recognizer.register_face(
            image=img,
            user_id=current_user.user_id,
            pose=pose_name,
            staff_number=current_user.staff_number,
        )

        if result["success"]:
            face_sample = FaceSample(
                user_id=current_user.user_id,
                pose=pose_name,
                image_path=result["image_path"],
                embedding_blob=result["embedding_bytes"],
                quality_score=int(result["quality_score"] * 100),
            )
            try:
                next_id = db.execute(text("SELECT face_samples_seq.NEXTVAL FROM dual")).scalar_one()
                face_sample.face_sample_id = int(next_id)
            except Exception:
                pass
            db.add(face_sample)
            results.append({
                "pose": pose_name,
                "success": True,
                "quality_score": result["quality_score"],
            })
        else:
            errors.append(f"{pose_name}: {result.get('error', 'failed')}")
            results.append({
                "pose": pose_name,
                "success": False,
                "error": result.get("error"),
            })

    # Mark user as face registered if at least front succeeded
    has_success = any(r["success"] for r in results)
    if has_success and current_user.face_registered != "Y":
        current_user.face_registered = "Y"
        current_user.profile_completed = "Y"
        current_user.updated_at = datetime.utcnow()

    # Audit log
    audit = AuditLog(
        user_id=current_user.user_id,
        action="multi_pose_registered",
        details=f"Multi-pose registration: {len(results)} poses, {len(errors)} errors: {'; '.join(errors) if errors else 'none'}",
    )
    db.add(audit)
    db.commit()
    db.refresh(current_user)

    logger.info(
        "multi_pose_registration_complete",
        extra={
            "user": current_user.username,
            "poses_registered": len(results),
            "errors": len(errors),
        },
    )

    return {
        "message": "Multi-pose registration completed" if has_success else "All poses failed",
        "results": results,
        "errors": errors,
        "user": current_user.username,
    }


@router.post("/login", status_code=status.HTTP_200_OK)
async def login_face(
    file: UploadFile,
    db: Session = Depends(get_db),
    recognizer: FaceRecognizer = Depends(get_recognizer),
) -> dict[str, object]:
    """Authenticate a user using face recognition.

    Full production pipeline:
        1. Decode uploaded image
        2. Detect face (SCRFD)
        3. Validate quality (blur, brightness, contrast, size, pose)
        4. Liveness detection (blink, texture, motion)
        5. Align face
        6. Generate ArcFace embedding
        7. Load all registered embeddings from Oracle
        8. Cosine similarity matching against gallery
        9. Authenticate if similarity exceeds threshold
        10. Generate JWT + log login event
    """
    # Step 1: Decode image
    image = _decode_upload_to_array(file)
    if image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or empty image file")

    # Step 2-6: Build gallery from all face samples with embeddings
    face_samples = (
        db.query(FaceSample)
        .filter(FaceSample.embedding_blob.isnot(None))
        .all()
    )

    if not face_samples:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No registered face data found in the system",
        )

    gallery = recognizer.build_gallery(face_samples)

    # Step 7: Run login pipeline
    login_result = recognizer.login_face(image, gallery)

    # Reset liveness state for next attempt
    recognizer.reset_liveness()

    if not login_result["authenticated"]:
        error_msg = login_result.get("error", "Face authentication failed - no matching face found")
        logger.debug("face_login_failed", extra={"error": error_msg})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)

    # Step 8: Look up the authenticated user
    user = db.query(User).filter(User.user_id == login_result["user_id"]).first()
    if not user or user.is_active != "Y":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive or not found")

    if user.is_locked == "Y":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is locked")

    # Step 9: Generate tokens
    access_token = create_access_token(user.username, {"login_method": "face"})
    refresh_token = create_refresh_token(user.username)

    # Step 10: Log the login event
    login_log = LoginLog(
        user_id=user.user_id,
        login_method="face",
        success="Y",
        ip_address=None,
        login_time=datetime.utcnow(),
    )
    db.add(login_log)

    # Step 11: Update user last login
    user.last_login_at = datetime.utcnow()
    user.failed_login_attempts = 0
    db.commit()

    logger.info(
        "face_login_success",
        extra={
            "user": user.username,
            "similarity": login_result["similarity"],
            "threshold": login_result["threshold"],
        },
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "similarity": login_result["similarity"],
        "threshold": login_result["threshold"],
        "liveness": {
            "score": login_result.get("liveness", {}).get("score"),
            "passed": login_result.get("liveness", {}).get("passed"),
        },
        "quality": {
            "score": login_result.get("checks", {}).get("blur", {}).get("value"),
            "checks": list(login_result.get("checks", {}).keys()),
        },
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.name if user.role else None,
            "department": user.department.name if user.department else None,
            "face_registered": user.face_registered,
        },
    }


@router.get("/status", status_code=status.HTTP_200_OK)
def face_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return the face registration status for the current user."""
    samples = db.query(FaceSample).filter(FaceSample.user_id == current_user.user_id).all()

    return {
        "face_registered": current_user.face_registered == "Y",
        "sample_count": len(samples),
        "poses": [s.pose for s in samples],
        "average_quality": (
            round(sum(s.quality_score or 0 for s in samples) / len(samples), 1)
            if samples
            else 0
        ),
    }

