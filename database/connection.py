from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.engine import Engine
from config import DATABASE_URL, DB_PATH
import os

class Base(DeclarativeBase):
    pass

# Ensure directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    pool_pre_ping=True
)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode, Foreign Keys, and optimal SQLite PRAGMAs for performance."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;")  # 64MB cache
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """Context-friendly database session factory."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def init_db():
    """Creates all database tables defined in models and applies schema migrations."""
    from database.models import Student, Department, Program, Venue, TimeSlot, ImportHistory, BackupHistory, AuditLog, AppSettings
    Base.metadata.create_all(bind=engine)

    # Auto-migration: ensure independent group/branch columns exist on students table
    with engine.connect() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(students)")
        columns = [row[1] for row in cursor.fetchall()]
        if "import_history_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN import_history_id INTEGER REFERENCES import_history(id)")
        if "group_venue_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN group_venue_id INTEGER REFERENCES venues(id)")
        if "group_time_slot_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN group_time_slot_id INTEGER REFERENCES time_slots(id)")
        if "group_venue_allocated_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN group_venue_allocated_at DATETIME")
        if "branch_venue_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN branch_venue_id INTEGER REFERENCES venues(id)")
        if "branch_time_slot_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN branch_time_slot_id INTEGER REFERENCES time_slots(id)")
        if "branch_venue_allocated_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE students ADD COLUMN branch_venue_allocated_at DATETIME")
        
        conn.commit()

