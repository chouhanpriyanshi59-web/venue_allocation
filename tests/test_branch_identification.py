import pytest
import pandas as pd
from pathlib import Path
from database.connection import init_db, SessionLocal
from database.models import Department, Student
from database.repository import Repository
from engine.data_importer import DataImporter

def test_usn_branch_mapping_and_non_merging():
    init_db()
    session = SessionLocal()
    try:
        # Clear existing data to run a clean test
        session.query(Student).delete()
        session.query(Department).delete()
        session.commit()

        # 1. Verify exact branch mappings for CE and CV
        dept_ce = Repository.get_or_create_department(session, "Chemical Engineering")
        dept_cv = Repository.get_or_create_department(session, "Civil Engineering")
        session.commit()

        assert dept_ce.code == "CE"
        assert dept_cv.code == "CV"
        assert dept_ce.id != dept_cv.id

        # 2. Test importing a mixed dataset with 30 CE students and 40 CV students
        # We will write a temporary CSV and import it.
        rows = []
        # 30 Chemical Engineering students (CE)
        for i in range(1, 31):
            rows.append({
                "Student ID": f"1RV26CE{i:03d}",
                "Student Full Name": f"Chemical Student {i}",
                "Branch / Department": "Chemical Engineering",
                "Program": "B.Tech",
                "Gender": "Male" if i % 2 == 0 else "Female"
            })
        # 40 Civil Engineering students (CV)
        for i in range(1, 41):
            rows.append({
                "Student ID": f"1RV26CV{i:03d}",
                "Student Full Name": f"Civil Student {i}",
                "Branch / Department": "Civil Engineering",
                "Program": "B.Tech",
                "Gender": "Male" if i % 2 == 0 else "Female"
            })

        df = pd.DataFrame(rows)
        temp_csv = Path("data/temp_test_import.csv")
        df.to_csv(temp_csv, index=False)

        # Mapping for the import
        mapping = {
            "Student ID": "student_id",
            "Student Full Name": "full_name",
            "Branch / Department": "department",
            "Program": "program",
            "Gender": "gender"
        }

        # Import
        result = DataImporter.import_excel(temp_csv, mapping)
        
        # Clean up temp file
        if temp_csv.exists():
            temp_csv.unlink()

        assert result["success"] is True
        assert result["new_students"] == 70

        # Verify DB counts for Chemical Engineering (CE)
        ce_count = session.query(Student).join(Department).filter(Department.code == "CE").count()
        assert ce_count == 30, f"Expected 30 Chemical Engineering students, found {ce_count}"

        # Verify DB counts for Civil Engineering (CV)
        cv_count = session.query(Student).join(Department).filter(Department.code == "CV").count()
        assert cv_count == 40, f"Expected 40 Civil Engineering students, found {cv_count}"

        # Verify specific USN allocations
        s_ce_1 = session.query(Student).filter(Student.usn == "1RV26CE001").first()
        assert s_ce_1 is not None
        assert s_ce_1.department.name == "Chemical Engineering"
        assert s_ce_1.department.code == "CE"

        s_ce_30 = session.query(Student).filter(Student.usn == "1RV26CE030").first()
        assert s_ce_30 is not None
        assert s_ce_30.department.name == "Chemical Engineering"
        assert s_ce_30.department.code == "CE"

        s_cv_1 = session.query(Student).filter(Student.usn == "1RV26CV001").first()
        assert s_cv_1 is not None
        assert s_cv_1.department.name == "Civil Engineering"
        assert s_cv_1.department.code == "CV"

        s_cv_40 = session.query(Student).filter(Student.usn == "1RV26CV040").first()
        assert s_cv_40 is not None
        assert s_cv_40.department.name == "Civil Engineering"
        assert s_cv_40.department.code == "CV"

    finally:
        session.close()
