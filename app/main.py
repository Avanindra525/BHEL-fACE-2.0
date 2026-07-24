"""FastAPI application entrypoint for FaceAuth Enterprise."""

from __future__ import annotations

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging import logger
from app.core.security import create_access_token
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.employees import router as employees_router
from app.api.routes.departments import router as departments_router
from app.api.routes.roles import router as roles_router
from app.api.routes.permissions import router as permissions_router
from app.api.routes.face import router as face_router
from app.api.routes.audit_logs import router as audit_logs_router
from app.api.routes.statistics import router as statistics_router
from app.api.routes.settings import router as settings_router
from app.api.routes.profile import router as profile_router
from app.api.routes.login_history import router as login_history_router
from app.setup_oracle import create_schema, validate_schema, inspect_constraint
from sqlalchemy.exc import IntegrityError


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> HTMLResponse:
    """Handle Oracle ORA-00001 / ORA-02289 constraint violations with detailed diagnostics."""
    import traceback
    from fastapi.responses import JSONResponse

    error_msg = str(exc.orig) if exc.orig else str(exc)
    logger.error("oracle_integrity_error", extra={"error": error_msg, "sql": str(exc.statement), "params": str(exc.params)})

    # Try to extract constraint name from ORA-00001 error
    constraint_name = None
    if "ORA-00001" in error_msg:
        # e.g. "ORA-00001: unique constraint (FACEAUTH.SYS_C007547) violated"
        import re
        match = re.search(r'unique constraint\s+\((.+?)\)', error_msg)
        if match:
            constraint_name = match.group(1).split(".")[-1]  # Just the constraint name, not schema

    diagnostics = {"error": "Database constraint violation", "detail": error_msg}
    if constraint_name:
        constraint_info = inspect_constraint(constraint_name)
        diagnostics["constraint"] = constraint_info
        diagnostics["message"] = (
            f"Unique constraint '{constraint_info.get('column_name', constraint_name)}' "
            f"on table '{constraint_info.get('table_name', 'unknown')}' violated. "
            f"This usually means a duplicate value was provided."
        )

    # Log full stack trace for debugging
    logger.error("integrity_error_stacktrace", extra={"traceback": "".join(traceback.format_exc())})

    return JSONResponse(status_code=409, content=diagnostics)

# ── Security Middleware ──────────────────────────────────────────────────
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware

app = FastAPI(title=settings.app_name, version="1.0.0", debug=settings.app_debug)

# CORS (must be first to handle preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(departments_router, prefix="/api/departments", tags=["departments"])
app.include_router(roles_router, prefix="/api/roles", tags=["roles"])
app.include_router(permissions_router, prefix="/api/permissions", tags=["permissions"])
app.include_router(face_router, prefix="/api/face", tags=["face"])
app.include_router(audit_logs_router, prefix="/api/audit-logs", tags=["audit-logs"])
app.include_router(statistics_router, prefix="/api/statistics", tags=["statistics"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(profile_router, prefix="/api/profile", tags=["profile"])
app.include_router(login_history_router, prefix="/api/login-history", tags=["login-history"])


@app.get("/", include_in_schema=False)
async def home_page(request: Request) -> HTMLResponse:
    """Serve the landing page for the application."""

    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health endpoint for runtime checks."""

    return {"status": "ok", "service": settings.app_name}


@app.get("/about", include_in_schema=False)
async def about_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="about.html")


@app.get("/contact", include_in_schema=False)
async def contact_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="contact.html")


@app.get("/login", include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/register", include_in_schema=False)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="register.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/admin", include_in_schema=False)
async def admin_dashboard_page(request: Request) -> HTMLResponse:
    db: Session = SessionLocal()
    try:
        from app.models.department import Department
        from app.models.permission import Permission
        from app.models.role import Role
        from app.models.user import User

        user_count = db.query(User).count()
        department_count = db.query(Department).count()
        role_count = db.query(Role).count()
        permission_count = db.query(Permission).count()
        face_registered_count = db.query(User).filter(User.face_registered == "Y").count()
    finally:
        db.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "user_count": user_count,
            "department_count": department_count,
            "role_count": role_count,
            "permission_count": permission_count,
            "face_registered_count": face_registered_count,
        },
    )


@app.get("/profile", include_in_schema=False)
async def profile_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="profile.html")


@app.get("/settings", include_in_schema=False)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html")


@app.get("/employees", include_in_schema=False)
async def employees_page(request: Request) -> HTMLResponse:
    db: Session = SessionLocal()
    try:
        from app.models.department import Department
        from app.models.user import User

        employees = db.query(User).order_by(User.created_at.desc()).all()
        departments = db.query(Department).all()
    finally:
        db.close()

    return templates.TemplateResponse(
        request=request,
        name="employees.html",
        context={"employees": employees, "departments": departments},
    )


@app.get("/departments", include_in_schema=False)
async def departments_page(request: Request) -> HTMLResponse:
    db: Session = SessionLocal()
    try:
        from app.models.department import Department
        from app.models.user import User

        departments = db.query(Department).order_by(Department.created_at.desc()).all()
        department_staff = {dept.department_id: db.query(User).filter(User.department_id == dept.department_id).count() for dept in departments}
    finally:
        db.close()

    return templates.TemplateResponse(
        request=request,
        name="departments.html",
        context={"departments": departments, "department_staff": department_staff},
    )


@app.post("/departments", include_in_schema=False)
async def create_department_from_form(name: str = Form(...), code: str | None = Form(default=None)) -> RedirectResponse:
    db: Session = SessionLocal()
    try:
        from app.models.department import Department

        department = Department(name=name, code=code or None)
        db.add(department)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/departments", status_code=303)


@app.get("/roles", include_in_schema=False)
async def roles_page(request: Request) -> HTMLResponse:
    db: Session = SessionLocal()
    try:
        from app.models.role import Role

        roles = db.query(Role).order_by(Role.created_at.desc()).all()
    finally:
        db.close()

    return templates.TemplateResponse(request=request, name="roles.html", context={"roles": roles})


@app.post("/roles", include_in_schema=False)
async def create_role_from_form(name: str = Form(...)) -> RedirectResponse:
    db: Session = SessionLocal()
    try:
        from app.models.role import Role

        role = Role(name=name)
        db.add(role)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/roles", status_code=303)


@app.get("/permissions", include_in_schema=False)
async def permissions_page(request: Request) -> HTMLResponse:
    db: Session = SessionLocal()
    try:
        from app.models.permission import Permission

        permissions = db.query(Permission).order_by(Permission.created_at.desc()).all()
    finally:
        db.close()

    return templates.TemplateResponse(request=request, name="permissions.html", context={"permissions": permissions})


@app.post("/permissions", include_in_schema=False)
async def create_permission_from_form(name: str = Form(...)) -> RedirectResponse:
    db: Session = SessionLocal()
    try:
        from app.models.permission import Permission

        permission = Permission(name=name)
        db.add(permission)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/permissions", status_code=303)


@app.get("/face-registration", include_in_schema=False)
async def face_registration_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="face_registration.html")


@app.get("/login-history", include_in_schema=False)
async def login_history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login_history.html")


@app.get("/statistics", include_in_schema=False)
async def statistics_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="statistics.html")


@app.get("/analytics", include_in_schema=False)
async def analytics_page(request: Request) -> HTMLResponse:
    """Full analytics dashboard with Chart.js, filters, and export."""
    db: Session = SessionLocal()
    try:
        from app.models.department import Department
        departments = db.query(Department).all()
    finally:
        db.close()
    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={"departments": departments},
    )


@app.get("/audit-logs", include_in_schema=False)
async def audit_logs_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="audit_logs.html")


@app.get("/403", include_in_schema=False)
async def forbidden_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="403.html")


@app.get("/404", include_in_schema=False)
async def not_found_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="404.html")


@app.get("/500", include_in_schema=False)
async def internal_error_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="500.html")


@app.on_event("startup")
def startup_event() -> None:
    """Initialize the database, validate Oracle schema, and sync sequences."""

    try:
        # Full schema initialization: validate connection, create tables, sync sequences
        create_schema()
    except RuntimeError as exc:
        # Connection validation failed (e.g. SYS/SYSTEM instead of FACEAUTH)
        logger.critical("startup_oracle_validation_failed", extra={"error": str(exc)})
        raise
    except Exception as exc:  # pragma: no cover - defensive startup handling
        logger.warning("startup_database_initialization_failed", extra={"error": str(exc)})

    logger.info("application_started", extra={"service": settings.app_name})
