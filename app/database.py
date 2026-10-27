from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL, logger

is_sqlite = "sqlite" in DATABASE_URL

engine_kwargs = {"echo": False}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 20}
else:
    # Production connection pool settings for PostgreSQL/MySQL
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(DATABASE_URL, **engine_kwargs)

# Enforce safe SQLite configuration (DELETE mode to avoid OneDrive/WSL .db-shm locking)
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=DELETE;")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA busy_timeout=10000;")
        except Exception:
            pass
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for obtaining a SQLAlchemy session with automatic closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
