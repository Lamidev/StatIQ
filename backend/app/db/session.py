from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
elif db_url.startswith("sqlite+aiosqlite:///"):
    db_url = db_url.replace("sqlite+aiosqlite:///", "sqlite:///")

connect_args = {}
if "sqlite" in db_url:
    connect_args = {
        "check_same_thread": False,
        "timeout": 30.0,
    }
elif "postgresql" in db_url:
    connect_args = {
        "sslmode": "require" if ("render.com" in db_url or "neon.tech" in db_url) else "prefer"
    }

try:
    engine = create_engine(db_url, echo=False, connect_args=connect_args, pool_pre_ping=True)

except Exception as e:
    print(f"[Database] Warning: Failed to connect to {db_url} ({e}). Falling back to local SQLite.")
    fallback_url = "sqlite:///./matchiq.db"
    engine = create_engine(fallback_url, echo=False, connect_args={"check_same_thread": False})



if "sqlite" in db_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


