# TODO: Simplify Face Registration - Remove Head Pose Validation

## Steps
- [x] 1. Analyze codebase and gather requirements
- [x] 2. Edit `app/face_ai/quality_check.py` — Remove all head pose estimation code
- [x] 3. Update `app/face_ai/recognizer.py` docstrings (remove pose validation references)
- [x] 4. Update `tests/test_face_ai.py` — Fix test_head_pose_tolerance test
- [x] 5. Cleaned up `__pycache__` to remove stale bytecode

## Summary of Changes

### `app/face_ai/quality_check.py`
- Removed `LANDMARK_IDX` class attribute
- Removed `max_yaw` and `max_pitch` from `__init__` parameters
- Removed `_check_head_pose()` method entirely (solvePnP, Rodrigues, Euler angle extraction)
- Removed `_check_head_pose()` call from `evaluate()` method
- Updated docstrings to remove head pose references

### `app/face_ai/recognizer.py`
- Updated registration pipeline docstring: "pose" → "eye visibility" in quality checks list

### `tests/test_face_ai.py`
- Renamed `test_head_pose_tolerance` → `test_eye_visibility_without_landmarks`
- Updated docstring to reflect eye visibility check

### Not Modified
- All frontend UI files (templates, CSS, JS)
- All API routes (`app/api/routes/face.py`)
- Oracle database models and schema
- Authentication flow in `auth_service.py`
- Liveness detection (head movement check was already a no-op)
- Face detection, embedding, alignment, matcher
- Config and thresholds

