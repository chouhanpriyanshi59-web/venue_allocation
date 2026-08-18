import pytest
import re
from database.connection import init_db, SessionLocal
from database.models import TimeSlot, Student
from database.repository import Repository
from services.export_service import ExportService

def test_slot_chronological_sorting_and_formatting():
    init_db()
    session = SessionLocal()
    try:
        # Clear existing student references to time slots to avoid foreign key errors
        session.query(Student).update({
            Student.time_slot_id: None,
            Student.group_time_slot_id: None,
            Student.branch_time_slot_id: None
        })
        session.query(TimeSlot).delete()
        session.commit()

        # Add slots in scrambled order (PM first, AM later)
        # Test 2: 1:00 PM - 3:00 PM
        Repository.get_or_create_time_slot(session, "Slot A", "1:00 PM", "3:00 PM")
        # Test 1: 9:00 AM - 10:00 AM
        Repository.get_or_create_time_slot(session, "Slot B", "9:00 AM", "10:00 AM")
        # Test 3: 9:30 AM - 10:45 AM
        Repository.get_or_create_time_slot(session, "Slot C", "9:30 AM", "10:45 AM")
        # Add another with no minutes to verify formatting of H:MM AM/PM
        Repository.get_or_create_time_slot(session, "Slot D", "2 PM", "4:15 PM")
        session.commit()

        # Run get_slot_timings
        s1, s2, s3, s4 = ExportService._get_slot_timings(session)

        # Expected chronological order:
        # 1. 9:00 AM - 10:00 AM
        # 2. 9:30 AM - 10:45 AM
        # 3. 1:00 PM - 3:00 PM
        # 4. 2:00 PM - 4:15 PM

        assert s1 == "9:00 AM - 10:00 AM"
        assert s2 == "9:30 AM - 10:45 AM"
        assert s3 == "1:00 PM - 3:00 PM"
        assert s4 == "2:00 PM - 4:15 PM"

    finally:
        session.close()

def test_group_name_cleaning():
    assert ExportService._clean_group_name("Group A") == "A"
    assert ExportService._clean_group_name("Group B") == "B"
    assert ExportService._clean_group_name("A") == "A"
    assert ExportService._clean_group_name("") == "Unassigned"
    assert ExportService._clean_group_name(None) == "Unassigned"
