"""Oracle 19c schema initialization, sequence synchronization, and runtime validation.

Automatically:
  1. Detects connection schema (rejects SYS/SYSTEM/CDB$ROOT)
  2. Creates tables if not present
  3. Creates all sequences if not present, synced to MAX(pk) + 1
  4. Validates sequence synchronization on every startup
  5. Provides detailed diagnostics for troubleshooting
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import Base, engine
from app.core.logging import logger
from app.models import (
    AuditLog,
    Department,
    FaceSample,
    LoginLog,
    PasswordHistory,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
)

# ─── Table metadata for sequence synchronization ──────────────────────────

TABLE_SEQUENCE_MAP = [
    ("users", "user_id", "users_seq"),
    ("departments", "department_id", "departments_seq"),
    ("roles", "role_id", "roles_seq"),
    ("permissions", "permission_id", "permissions_seq"),
    ("role_permissions", "role_permission_id", "role_permissions_seq"),
    ("face_samples", "face_sample_id", "face_samples_seq"),
    ("login_logs", "login_log_id", "login_logs_seq"),
    ("audit_logs", "audit_log_id", "audit_logs_seq"),
    ("refresh_tokens", "refresh_token_id", "refresh_tokens_seq"),
    ("password_history", "password_history_id", "password_history_seq"),
]


# ─── Connection Validation ────────────────────────────────────────────────


                    DECLARE
                        v_max_id NUMBER;
                        v_curr_val NUMBER;
                    BEGIN
                        EXECUTE IMMEDIATE 'SELECT COALESCE(MAX({pk_column}), 0) + 1 FROM {table_name}' INTO v_max_id;
                        SELECT {sequence_name}.NEXTVAL INTO v_curr_val FROM dual;
                        IF v_curr_val < v_max_id THEN
                            EXECUTE IMMEDIATE 'DROP SEQUENCE {sequence_name}';
                            EXECUTE IMMEDIATE 'CREATE SEQUENCE {sequence_name} START WITH ' || v_max_id || ' INCREMENT BY 1 NOCACHE';
                        END IF;
                    END;
                    """
                ),
            )


def create_schema() -> None:
    """Create all ORM tables in the connected Oracle database."""

    Base.metadata.create_all(bind=engine)
    create_sequences()
    with engine.begin() as connection:
        connection.execute(text("COMMENT ON TABLE users IS 'FaceAuth Enterprise users'"))
        connection.execute(text("COMMENT ON TABLE departments IS 'FaceAuth Enterprise departments'"))
        connection.execute(text("COMMENT ON TABLE roles IS 'FaceAuth Enterprise roles'"))
        connection.execute(text("COMMENT ON TABLE permissions IS 'FaceAuth Enterprise permissions'"))
        connection.execute(text("COMMENT ON TABLE role_permissions IS 'FaceAuth Enterprise role-permission assignments'"))
        connection.execute(text("COMMENT ON TABLE face_samples IS 'FaceAuth Enterprise face samples'"))
        connection.execute(text("COMMENT ON TABLE login_logs IS 'FaceAuth Enterprise login logs'"))
        connection.execute(text("COMMENT ON TABLE audit_logs IS 'FaceAuth Enterprise audit logs'"))
        connection.execute(text("COMMENT ON TABLE refresh_tokens IS 'FaceAuth Enterprise refresh tokens'"))
        connection.execute(text("COMMENT ON TABLE password_history IS 'FaceAuth Enterprise password history'"))


if __name__ == "__main__":
    create_schema()
    print("Oracle schema created successfully")
