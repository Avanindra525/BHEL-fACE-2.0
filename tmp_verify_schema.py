from sqlalchemy import create_engine, text
from app.core.config import settings
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    for table in ['USERS','DEPARTMENTS','ROLES','PERMISSIONS','ROLE_PERMISSIONS','FACE_SAMPLES','LOGIN_LOGS','AUDIT_LOGS','REFRESH_TOKENS','PASSWORD_HISTORY']:
        result = conn.execute(text("SELECT COUNT(*) FROM user_tables WHERE table_name = :name"), {'name': table})
        print(table, result.scalar())
