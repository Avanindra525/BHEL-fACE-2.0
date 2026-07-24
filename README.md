# FaceAuth Enterprise

FaceAuth Enterprise is a production-oriented facial recognition authentication system built with FastAPI, Oracle Database 19c, SQLAlchemy 2.x, Pydantic v2, and a Bootstrap 5 frontend.

## Core stack

- Python 3.12
- FastAPI and Uvicorn
- Oracle Database 19c with python-oracledb
- SQLAlchemy 2.x and Alembic
- JWT, bcrypt, refresh tokens
- OpenCV-compatible image processing and face workflow modules
- Pytest for testing

## Getting started

1. Copy `.env.example` to `.env` and set the Oracle credentials, JWT secret, and upload directory.
2. Install dependencies with `pip install -r requirements.txt`.
3. Start the application with `uvicorn app.main:app --reload`.
4. Open `http://127.0.0.1:8000/` for the landing page and `http://127.0.0.1:8000/docs` for the FastAPI Swagger UI.

## Verification

The project has been verified with:

- `python -m pytest -q` → 2 passed
- `python -m compileall app` → completed successfully

## Notes

- The application is structured for Oracle 19c only and uses SQLAlchemy-compatible ORM models with Oracle-friendly column types.
- A real Oracle instance is required for persisted storage and full multi-user workflows.
- Static uploads are written to `app/static/uploads` by default.
