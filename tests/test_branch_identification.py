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

        # 1. Verify exact branch mappings for CHEM and CIVIL
        dept_ce = Repository.get_or_create_department(session, "Chemical Engineering")
        dept_cv = Repository.get_or_create_department(session, "Civil Engineering")
        session.commit()

        assert dept_ce.code == "CHEM"
        assert dept_cv.code == "CIVIL"
        assert dept_ce.id != dept_cv.id

        # 2. Test importing a mixed dataset with 30 CHEM students and 40 CIVIL students
        # We will write a temporary CSV and import it.
        rows = []
        # 30 Chemical Engineering students (CHEM)
        for i in range(1, 31):
            rows.append({
                "SIN": f"1RV26CE{i:03d}",
                "STUDENT FULL NAME": f"Chemical Student {i}",
                "PROGRAM": "B.E 2025 SCHEME - CHEMICAL ENGINEERING",
                "GENDER": "Male" if i % 2 == 0 else "Female"
            })
        # 40 Civil Engineering students (CIVIL)
        for i in range(1, 41):
            rows.append({
                "SIN": f"1RV26CV{i:03d}",
                "STUDENT FULL NAME": f"Civil Student {i}",
                "PROGRAM": "B.E 2025 SCHEME - CIVIL ENGINEERING",
                "GENDER": "Male" if i % 2 == 0 else "Female"
            })

        df = pd.DataFrame(rows)
        temp_csv = Path("data/temp_test_import.csv")
        df.to_csv(temp_csv, index=False)

        # Mapping for the import
        mapping = {
            "SIN": "sin",
            "STUDENT FULL NAME": "full_name",
            "PROGRAM": "program",
            "GENDER": "gender"
        }

        # Import
        result = DataImporter.import_excel(temp_csv, mapping)
        
        # Clean up temp file
        if temp_csv.exists():
            temp_csv.unlink()

        assert result["success"] is True
        assert result["new_students"] == 70

        # Verify DB counts for Chemical Engineering (CHEM)
        ce_count = session.query(Student).join(Department).filter(Department.code == "CHEM").count()
        assert ce_count == 30, f"Expected 30 Chemical Engineering students, found {ce_count}"

        # Verify DB counts for Civil Engineering (CIVIL)
        cv_count = session.query(Student).join(Department).filter(Department.code == "CIVIL").count()
        assert cv_count == 40, f"Expected 40 Civil Engineering students, found {cv_count}"

        # Verify specific SIN allocations
        s_ce_1 = session.query(Student).filter(Student.usn == "1RV26CE001").first()
        assert s_ce_1 is not None
        assert s_ce_1.department.name == "Chemical Engineering"
        assert s_ce_1.department.code == "CHEM"

        s_ce_30 = session.query(Student).filter(Student.usn == "1RV26CE030").first()
        assert s_ce_30 is not None
        assert s_ce_30.department.name == "Chemical Engineering"
        assert s_ce_30.department.code == "CHEM"

        s_cv_1 = session.query(Student).filter(Student.usn == "1RV26CV001").first()
        assert s_cv_1 is not None
        assert s_cv_1.department.name == "Civil Engineering"
        assert s_cv_1.department.code == "CIVIL"

        s_cv_40 = session.query(Student).filter(Student.usn == "1RV26CV040").first()
        assert s_cv_40 is not None
        assert s_cv_40.department.name == "Civil Engineering"
        assert s_cv_40.department.code == "CIVIL"

    finally:
        session.close()
