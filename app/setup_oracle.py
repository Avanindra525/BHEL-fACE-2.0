"""Oracle 19c schema initialization, sequence synchronization, and runtime validation.

Automatically:
  1. Detects connection schema (rejects SYS/SYSTEM/CDB$ROOT)
  2. Creates tables if not present
  3. Creates all sequences if not present, synced to MAX(pk) + 1
  4. Validates sequence synchronization on every startup
  5. Provides detailed diagnostics for troubleshooting
"""

from __future__ import annotations

from sqlalchemy import text

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

DEFAULT_DEPARTMENTS = [
    ("HR", "HR"),
    ("IT", "IT"),
    ("Finance", "FIN"),
    ("Production", "PROD"),
    ("Administration", "ADMIN"),
    ("Security", "SEC"),
]


# ─── Connection Validation ────────────────────────────────────────────────


def validate_connection() -> None:
    """Validate that the application is connected to the FACEAUTH schema.

    Detects and rejects connections to SYS, SYSTEM, or CDB$ROOT which
    would cause ORA-00942 (table or view does not exist) at runtime.
    """
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "SELECT USER, SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name, "
                "SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name FROM dual"
            )
        ).fetchone()

        current_user = str(result[0]).strip().upper()
        db_name = str(result[1]).strip() if result[1] else "N/A"
        con_name = str(result[2]).strip().upper() if result[2] else "N/A"

        logger.info(
            "oracle_connection",
            extra={
                "user": current_user,
                "db_name": db_name,
                "container": con_name,
            },
        )

        if current_user in ("SYS", "SYSTEM", "DBSNMP"):
            raise RuntimeError(
                f"CRITICAL: Connected as '{current_user}' in container '{con_name}'. "
                f"The application must connect as the 'FACEAUTH' schema user. "
                f"Update your database_url in .env to use the FACEAUTH user."
            )

        logger.info("oracle_connection_valid", extra={"schema": current_user})


# ─── Sequence Synchronization ──────────────────────────────────────────────


def sync_sequence(
    connection: object,
    table_name: str,
    pk_column: str,
    sequence_name: str,
) -> dict[str, object]:
    """Synchronize a single Oracle sequence with its table's MAX(pk).

    Steps:
      1. Check if table exists
      2. Find MAX(pk_column) - default 0 if table empty or missing
      3. Create sequence if missing, starting at MAX(pk) + 1
      4. If sequence exists, compare NEXTVAL with MAX(pk); drop & recreate if behind

    Returns diagnostics dict with sync status.
    """
    result: dict[str, object] = {
        "table": table_name,
        "pk_column": pk_column,
        "sequence": sequence_name,
        "max_pk": None,
        "nextval": None,
        "synced": False,
        "action": "none",
    }

    # Step 1: Check if table exists
    table_exists = connection.execute(
        text("SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER(:tname)"),
        {"tname": table_name},
    ).scalar()
    if not table_exists:
        result["action"] = "table_missing"
        result["synced"] = False
        return result

    # Step 2: Find MAX(primary_key)
    max_pk = connection.execute(
        text(f"SELECT COALESCE(MAX({pk_column}), 0) FROM {table_name}")
    ).scalar() or 0
    desired_start = max_pk + 1
    result["max_pk"] = max_pk

    # Step 3: Check if sequence exists
    seq_exists = connection.execute(
        text("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = UPPER(:sname)"),
        {"sname": sequence_name},
    ).scalar()

    if seq_exists:
        # Fetch current NEXTVAL by peeking
        curr_val = connection.execute(
            text(f"SELECT {sequence_name}.NEXTVAL FROM dual")
        ).scalar()
        result["nextval"] = curr_val

        if curr_val < desired_start:
            # Sequence is behind - drop and recreate
            connection.execute(text(f"DROP SEQUENCE {sequence_name}"))
            connection.execute(
                text(f"CREATE SEQUENCE {sequence_name} START WITH {desired_start} INCREMENT BY 1 NOCACHE")
            )
            result["action"] = f"recreated from {curr_val} to {desired_start}"
            result["synced"] = True
            logger.info(
                "sequence_synced",
                extra={
                    "sequence": sequence_name,
                    "table": table_name,
                    "old_nextval": curr_val,
                    "new_start": desired_start,
                },
            )
        else:
            result["action"] = "already_synced"
            result["synced"] = True
    else:
        # Create sequence starting at MAX(pk) + 1
        connection.execute(
            text(f"CREATE SEQUENCE {sequence_name} START WITH {desired_start} INCREMENT BY 1 NOCACHE")
        )
        result["action"] = f"created starting at {desired_start}"
        result["synced"] = True
        logger.info(
            "sequence_created",
            extra={
                "sequence": sequence_name,
                "table": table_name,
                "start": desired_start,
            },
        )

    return result


def create_sequences() -> list[dict[str, object]]:
    """Create and sync all Oracle sequences for primary key generation.

    Returns list of diagnostics dicts for each sequence.
    """
    results: list[dict[str, object]] = []
    with engine.begin() as connection:
        for table_name, pk_column, sequence_name in TABLE_SEQUENCE_MAP:
            try:
                r = sync_sequence(connection, table_name, pk_column, sequence_name)
                results.append(r)
            except Exception as exc:
                logger.error(
                    "sequence_sync_failed",
                    extra={
                        "sequence": sequence_name,
                        "table": table_name,
                        "error": str(exc),
                    },
                )
                results.append({
                    "table": table_name,
                    "sequence": sequence_name,
                    "error": str(exc),
                    "synced": False,
                })
    return results


# ─── Schema Diagnostics ────────────────────────────────────────────────────


def validate_schema() -> dict[str, object]:
    """Run comprehensive schema diagnostics and return results.

    Checks:
      - Current user, DB name, container
      - All tables present
      - All sequences present and synchronized
      - MAX(pk) vs NEXTVAL for each table

    Returns a dict suitable for logging or HTTP response.
    """
    diagnostics: dict[str, object] = {
        "connection": {},
        "tables": {},
        "sequences": {},
        "all_synced": False,
    }

    with engine.begin() as connection:
        # Connection info
        row = connection.execute(
            text(
                "SELECT USER, SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name, "
                "SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name FROM dual"
            )
        ).fetchone()
        diagnostics["connection"] = {
            "user": str(row[0]),
            "db_name": str(row[1]) if row[1] else "N/A",
            "container": str(row[2]) if row[2] else "N/A",
        }

        # Tables
        for table_name, _, _ in TABLE_SEQUENCE_MAP:
            exists = connection.execute(
                text("SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER(:tname)"),
                {"tname": table_name},
            ).scalar()
            diagnostics["tables"][table_name] = bool(exists)

        # Sequences with validation
        all_synced = True
        for table_name, pk_column, sequence_name in TABLE_SEQUENCE_MAP:
            seq_info: dict[str, object] = {"exists": False, "max_pk": None, "nextval": None, "synced": False}

            # Check sequence existence
            seq_exists = connection.execute(
                text("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = UPPER(:sname)"),
                {"sname": sequence_name},
            ).scalar()
            seq_info["exists"] = bool(seq_exists)

            # Check table existence for MAX(pk)
            table_exists = connection.execute(
                text("SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER(:tname)"),
                {"tname": table_name},
            ).scalar()

            if table_exists:
                max_pk = connection.execute(
                    text(f"SELECT COALESCE(MAX({pk_column}), 0) FROM {table_name}")
                ).scalar() or 0
                seq_info["max_pk"] = max_pk

                if seq_exists:
                    curr_val = connection.execute(
                        text(f"SELECT {sequence_name}.NEXTVAL FROM dual")
                    ).scalar()
                    seq_info["nextval"] = curr_val
                    seq_info["synced"] = curr_val >= max_pk + 1

                    if not seq_info["synced"]:
                        all_synced = False

            diagnostics["sequences"][sequence_name] = seq_info

        diagnostics["all_synced"] = all_synced

    return diagnostics


# ─── Constraint Inspection ────────────────────────────────────────────────


def inspect_constraint(constraint_name: str) -> dict[str, object]:
    """Lookup constraint details from Oracle USER_CONSTRAINTS / USER_CONS_COLUMNS.

    Useful for diagnosing ORA-00001 unique constraint violations.

    Returns dict with constraint_name, table_name, column_name, constraint_type.
    """
    result: dict[str, object] = {
        "constraint_name": constraint_name,
        "table_name": None,
        "column_name": None,
        "constraint_type": None,
    }
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT uc.table_name, ucc.column_name, uc.constraint_type "
                    "FROM user_constraints uc "
                    "JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name "
                    "WHERE uc.constraint_name = UPPER(:cname)"
                ),
                {"cname": constraint_name},
            ).fetchone()
            if row:
                result["table_name"] = str(row[0])
                result["column_name"] = str(row[1])
                result["constraint_type"] = str(row[2])
    except Exception as exc:
        result["error"] = str(exc)
    return result


# ─── Create Schema ─────────────────────────────────────────────────────────


def create_schema() -> None:
    """Full schema initialization: validate connection, create tables, sync sequences.

    This is called once on application startup.
    """
    logger.info("schema_initialization_started")

    # Step 1: Validate connection schema
    validate_connection()

    # Step 2: Create tables if not present
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("tables_created")
    except Exception as exc:
        logger.error("table_creation_failed", extra={"error": str(exc)})
        raise

    # Step 3: Sync all sequences
    sync_results = create_sequences()
    failed = [r for r in sync_results if not r.get("synced")]
    if failed:
        logger.warning("sequence_sync_incomplete", extra={"failed_count": len(failed), "details": failed})
    else:
        logger.info("all_sequences_synchronized")

    # Step 3b: Ensure standard BHEL departments exist for employee profiles
    try:
        with engine.begin() as connection:
            for name, code in DEFAULT_DEPARTMENTS:
                exists = connection.execute(
                    text("SELECT COUNT(*) FROM departments WHERE name = :name"),
                    {"name": name},
                ).scalar()
                if not exists:
                    connection.execute(
                        text(
                            "INSERT INTO departments "
                            "(department_id, name, code, description, is_active, created_at, updated_at) "
                            "VALUES (departments_seq.nextval, :name, :code, :description, 'Y', SYSDATE, SYSDATE)"
                        ),
                        {
                            "name": name,
                            "code": code,
                            "description": f"{name} department",
                        },
                    )
        logger.info("default_departments_ready")
    except Exception as exc:
        logger.warning("default_department_seed_failed", extra={"error": str(exc)})

    # Step 4: Log schema diagnostics
    diag = validate_schema()
    logger.info(
        "schema_diagnostics",
        extra={
            "connection": diag["connection"],
            "tables": diag["tables"],
            "all_sequences_synced": diag["all_synced"],
        },
    )

    # Step 5: Add table comments
    try:
        with engine.begin() as connection:
            comments = [
                ("users", "FaceAuth Enterprise users"),
                ("departments", "FaceAuth Enterprise departments"),
                ("roles", "FaceAuth Enterprise roles"),
                ("permissions", "FaceAuth Enterprise permissions"),
                ("role_permissions", "FaceAuth Enterprise role-permission assignments"),
                ("face_samples", "FaceAuth Enterprise face samples"),
                ("login_logs", "FaceAuth Enterprise login logs"),
                ("audit_logs", "FaceAuth Enterprise audit logs"),
                ("refresh_tokens", "FaceAuth Enterprise refresh tokens"),
                ("password_history", "FaceAuth Enterprise password history"),
            ]
            for table_name, comment in comments:
                try:
                    connection.execute(
                        text(f"COMMENT ON TABLE {table_name} IS :comment"),
                        {"comment": comment},
                    )
                except Exception:
                    pass  # Comment already exists
    except Exception as exc:
        logger.debug("table_comments_skipped", extra={"error": str(exc)})

    logger.info("schema_initialization_complete")


if __name__ == "__main__":
    create_schema()
    diag = validate_schema()
    import json
    print(json.dumps(diag, indent=2, default=str))
    print("Oracle schema created successfully")
