"""Create the Oracle schema objects required by FaceAuth Enterprise."""

from __future__ import annotations

from sqlalchemy import text

from app.core.database import Base, engine
from app.models import AuditLog, Department, FaceSample, LoginLog, PasswordHistory, Permission, RefreshToken, Role, RolePermission, User


def create_sequences() -> None:
    """Create Oracle sequences for each table so primary keys can be generated automatically."""

    tables = [
        "users",
        "departments",
        "roles",
        "permissions",
        "role_permissions",
        "face_samples",
        "login_logs",
        "audit_logs",
        "refresh_tokens",
        "password_history",
    ]
    with engine.begin() as connection:
        for table_name in tables:
            sequence_name = f"{table_name}_seq"
            connection.execute(
                text(
                    f"""
                    DECLARE
                        v_count NUMBER;
                    BEGIN
                        SELECT COUNT(*) INTO v_count FROM user_sequences WHERE sequence_name = UPPER(:sequence_name);
                        IF v_count = 0 THEN
                            EXECUTE IMMEDIATE 'CREATE SEQUENCE {sequence_name} START WITH 1 INCREMENT BY 1 NOCACHE';
                        END IF;
                    END;
                    """
                ),
                {"sequence_name": sequence_name.upper()},
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
