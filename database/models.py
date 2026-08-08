from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Boolean, Float, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    students: Mapped[List["Student"]] = relationship("Student", back_populates="department")

class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    students: Mapped[List["Student"]] = relationship("Student", back_populates="program")

class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    students: Mapped[List["Student"]] = relationship("Student", foreign_keys="Student.venue_id", back_populates="venue")

class TimeSlot(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g., "09:00 AM"
    end_time: Mapped[str] = mapped_column(String(20), nullable=False)    # e.g., "11:00 AM"
    day_number: Mapped[int] = mapped_column(Integer, default=1)

    students: Mapped[List["Student"]] = relationship("Student", foreign_keys="Student.time_slot_id", back_populates="time_slot")

    __table_args__ = (
        UniqueConstraint('slot_name', 'day_number', name='uq_slot_day'),
    )

class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usn: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    student_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    student_number: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    gender: Mapped[str] = mapped_column(String(20), default="Unknown", index=True)
    status: Mapped[str] = mapped_column(String(20), default="Active", index=True)

    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    program_id: Mapped[Optional[int]] = mapped_column(ForeignKey("programs.id"), nullable=True, index=True)
    import_history_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_history.id"), nullable=True, index=True)

    group_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    time_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("time_slots.id"), nullable=True, index=True)

    # Independent Group-wise Venue Allocation
    group_venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    group_time_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("time_slots.id"), nullable=True, index=True)
    group_venue_allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Independent Branch-wise Venue Allocation
    branch_venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    branch_time_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("time_slots.id"), nullable=True, index=True)
    branch_venue_allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    group_allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    venue_allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="students")
    program: Mapped[Optional["Program"]] = relationship("Program", back_populates="students")
    venue: Mapped[Optional["Venue"]] = relationship("Venue", foreign_keys=[venue_id], back_populates="students")
    time_slot: Mapped[Optional["TimeSlot"]] = relationship("TimeSlot", foreign_keys=[time_slot_id], back_populates="students")
    
    group_venue: Mapped[Optional["Venue"]] = relationship("Venue", foreign_keys=[group_venue_id])
    group_time_slot: Mapped[Optional["TimeSlot"]] = relationship("TimeSlot", foreign_keys=[group_time_slot_id])
    branch_venue: Mapped[Optional["Venue"]] = relationship("Venue", foreign_keys=[branch_venue_id])
    branch_time_slot: Mapped[Optional["TimeSlot"]] = relationship("TimeSlot", foreign_keys=[branch_time_slot_id])
    
    import_history: Mapped[Optional["ImportHistory"]] = relationship("ImportHistory", back_populates="students")

class ImportHistory(Base):
    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    new_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_records: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    students: Mapped[List["Student"]] = relationship("Student", back_populates="import_history")

class BackupHistory(Base):
    __tablename__ = "backup_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_action: Mapped[str] = mapped_column(String(100), nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AppSettings(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
