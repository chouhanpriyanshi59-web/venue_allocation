import pytest
from engine.column_mapper import ColumnMapper

def test_column_mapper_exact_and_fuzzy():
    headers = [
        "Candidate Name",
        "Univ USN",
        "Branch / Department",
        "M/F",
        "Extra Random Column"
    ]
    mapping, unmapped, missing_required = ColumnMapper.map_columns(headers)

    assert mapping["Candidate Name"] == "full_name"
    assert mapping["Univ USN"] == "student_id"
    assert mapping["Branch / Department"] == "department"
    assert mapping["M/F"] == "gender"
    assert "Extra Random Column" in unmapped
    assert len(missing_required) == 0

def test_column_mapper_missing_required():
    headers = ["Candidate Name", "Random Header"]
    mapping, unmapped, missing_required = ColumnMapper.map_columns(headers)

    assert "Student ID" in missing_required
    assert "Branch / Department" in missing_required

def test_idempotent_department_get_or_create():
    from database.connection import init_db, SessionLocal
    from database.models import Department, Student
    from database.repository import Repository

    init_db()
    session = SessionLocal()
    try:
        session.query(Student).delete()
        session.query(Department).delete()
        session.commit()

        # 1. Create a department
        d1 = Repository.get_or_create_department(session, "Computer Science & Engineering", code="CSE")
        session.commit()
        assert d1.code == "CSE"

        # 2. Query with variation in name that generates same code or uses existing code
        d2 = Repository.get_or_create_department(session, "CSE")
        assert d2.id == d1.id

        d3 = Repository.get_or_create_department(session, "Computer Science Engineering")
        assert d3.id == d1.id

        assert session.query(Department).count() == 1
    finally:
        session.close()

def test_delete_import_history_removes_students():
    from database.connection import init_db, SessionLocal
    from database.models import Student, ImportHistory
    from database.repository import Repository

    init_db()
    session = SessionLocal()
    try:
        session.query(Student).delete()
        session.query(ImportHistory).delete()
        session.commit()

        # Create import history
        imp = ImportHistory(file_name="test_500.csv", file_hash="hash123", total_rows=500, new_records=500)
        session.add(imp)
        session.flush()

        # Create students linked to import
        for i in range(10):
            s = Student(usn=f"1DS21TEST{i:03d}", full_name=f"Student {i}", import_history_id=imp.id)
            session.add(s)
        session.commit()

        assert session.query(Student).count() == 10

        # Delete import history
        ok, msg = Repository.delete_import_history(session, imp.id)
        assert ok is True
        assert session.query(Student).count() == 0
        assert session.query(ImportHistory).filter(ImportHistory.id == imp.id).first() is None
    finally:
        session.close()
