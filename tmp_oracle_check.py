from sqlalchemy import create_engine, text
DATABASE_URL = 'oracle+oracledb://faceauth:FaceAuth123@localhost:1521?service_name=orcl'
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    print(conn.execute(text("SELECT 'Oracle Connected Successfully' FROM dual")).fetchone())
