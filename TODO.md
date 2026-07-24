# Completed Fixes

## ✅ Fix 1: Head Pose Validation Removed
- `app/face_ai/quality_check.py` — Removed solvePnP, yaw/pitch/roll estimation, LANDMARK_IDX
- `app/face_ai/recognizer.py` — Updated docstrings

## ✅ Fix 2: Oracle ORA-01400 Primary Key Fix
- All 10 models: replaced `autoincrement=True` with `Sequence("table_name_seq")`
- `app/api/routes/face.py` — Removed manual NEXTVAL hacks
- `app/repositories/base.py` — Removed `_assign_primary_key()` fallback

## ✅ Fix 3: Oracle ORA-00001 Sequence Sync
- `app/setup_oracle.py` — Added sequence syncing to `MAX(pk_id) + 1` after creation

## Steps to resolve ORA-00001
1. Run `setup_oracle.py` or restart the app (startup event calls `create_sequences()`)
2. This will sync all sequences to `MAX(id) + 1` so they don't conflict with existing rows
3. The login should then succeed

