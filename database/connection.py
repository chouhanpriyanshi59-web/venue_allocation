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
    from database.models import Student, Department, Program, Venue, TimeSlot, ImportHistory, BackupHistory, AuditLog, AppSettings, AllocationRun
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
        
        # Auto-migration for venues
        cursor = conn.exec_driver_sql("PRAGMA table_info(venues)")
        venues_cols = [row[1] for row in cursor.fetchall()]
        if "group_name" not in venues_cols:
            conn.exec_driver_sql("ALTER TABLE venues ADD COLUMN group_name VARCHAR(50)")
        
        conn.exec_driver_sql("DROP INDEX IF EXISTS ix_venues_name")
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ix_venues_name_group ON venues (name, group_name)")

        # Auto-migration for time_slots
        cursor = conn.exec_driver_sql("PRAGMA table_info(time_slots)")
        time_slots_cols = [row[1] for row in cursor.fetchall()]
        if "group_name" not in time_slots_cols:
            conn.exec_driver_sql("ALTER TABLE time_slots RENAME TO time_slots_old")
            conn.exec_driver_sql("""
                CREATE TABLE time_slots (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    slot_name VARCHAR(50) NOT NULL,
                    start_time VARCHAR(20) NOT NULL,
                    end_time VARCHAR(20) NOT NULL,
                    day_number INTEGER NOT NULL,
                    group_name VARCHAR(50),
                    CONSTRAINT uq_slot_day_group UNIQUE (slot_name, day_number, group_name)
                )
            """)
            conn.exec_driver_sql("""
                INSERT INTO time_slots (id, slot_name, start_time, end_time, day_number, group_name)
                SELECT id, slot_name, start_time, end_time, day_number, NULL FROM time_slots_old
            """)
            conn.exec_driver_sql("DROP TABLE time_slots_old")

        conn.commit()

