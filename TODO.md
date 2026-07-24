# TODO: Simplify Face Registration - Remove Head Pose Validation

## Steps
- [x] 1. Analyze codebase and gather requirements
- [x] 2. Edit `app/face_ai/quality_check.py` — Remove all head pose estimation code
- [x] 3. Update `app/face_ai/recognizer.py` docstrings (remove pose validation references)
- [x] 4. Update `tests/test_face_ai.py` — Fix test_head_pose_tolerance test
- [x] 5. Cleaned up `__pycache__` to remove stale bytecode
- [x] 6. Verified all modified files parse correctly
- [x] 7. Ran tests — 20 passed, no regressions from changes

## Summary of Changes

### `app/face_ai/quality_check.py`
- Removed `LANDMARK_IDX` class attribute (unused)
- Removed `max_yaw` and `max_pitch` from `__init__` parameters
- Removed entire `_check_head_pose()` method (solvePnP, Rodrigues, Euler angle extraction, yaw/pitch/roll thresholds)
- Removed `_check_head_pose()` call from `evaluate()` method
- Updated docstrings to remove head pose references

### `app/face_ai/recognizer.py`
- Updated registration pipeline docstring: "pose" → "eye visibility" in quality checks list

### `tests/test_face_ai.py`
- Renamed `test_head_pose_tolerance` → `test_eye_visibility_without_landmarks`
- Fixed assertion to properly verify expected behavior

### Not Modified
- All frontend UI files (templates, CSS, JS)
- All API routes (`app/api/routes/face.py`)
- Oracle database models and schema
- Authentication flow in `auth_service.py`
- Liveness detection (separate from pose validation)
- Face detection, embedding, alignment, matcher
- Config and thresholds
- Login workflow
- Dashboard

