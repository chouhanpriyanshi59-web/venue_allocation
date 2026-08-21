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
    assert ExportService._clean_group_name("Group A") == "Group A"
    assert ExportService._clean_group_name("Group B") == "Group B"
    assert ExportService._clean_group_name("A") == "Group A"
    assert ExportService._clean_group_name("") == "Unassigned"
    assert ExportService._clean_group_name(None) == "Unassigned"


def test_excel_export_branch_and_group_format(tmp_path):
    import openpyxl
    from database.models import Program, Department, Student
    
    init_db()
    session = SessionLocal()
    try:
        session.query(Student).delete()
        session.query(Department).delete()
        session.query(Program).delete()
        session.commit()
        
        dept = Department(name="Electronics", code="ECE")
        session.add(dept)
        session.flush()
        
        prog = Program(name="B.E 2025 SCHEME - ELECTRONICS AND COMM", code="ECE-2025")
        session.add(prog)
        session.flush()
        
        s = Student(
            usn="1DS21EC001",
            full_name="Test Student",
            gender="Male",
            department_id=dept.id,
            program_id=prog.id,
            group_name="Group A",
            status="Active"
        )
        session.add(s)
        session.commit()
        
        export_file = tmp_path / "group_wise.xlsx"
        ExportService.export_group_wise_excel(export_file)
        
        wb = openpyxl.load_workbook(export_file)
        ws = wb.active
        
        row2_vals = [cell.value for cell in ws[2]]
        assert row2_vals[4] == "B.E 2025 SCHEME - ELECTRONICS AND COMM"
        assert row2_vals[5] == "Group A"
        
    finally:
        session.close()
