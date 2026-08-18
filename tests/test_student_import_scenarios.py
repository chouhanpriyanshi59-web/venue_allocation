import pytest
import pandas as pd
from pathlib import Path
from database.connection import init_db, SessionLocal
from database.models import Student, Department, Program
from engine.data_importer import DataImporter, identify_department
from core.exceptions import ValidationError

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    session = SessionLocal()
    session.query(Student).delete()
    session.query(Department).delete()
    session.query(Program).delete()
    session.commit()
    session.close()

def test_department_identification_scenarios():
    # Test 1: CSE
    code, name = identify_department("B.E 2025 SCHEME - COMPUTER SCIENCE")
    assert code == "CSE"
    assert name == "Computer Science Engineering"

    # Test 2: AIML
    code, name = identify_department("B.E 2025 SCHEME - CSE(AI&ML)")
    assert code == "AIML"
    
    # Test 3: ECE
    code, name = identify_department("B.E 2025 SCHEME - ELECTRONICS & COMM")
    assert code == "ECE"

    # Test 4: Chemical
    code, name = identify_department("B.E 2025 SCHEME - CHEMICAL ENGINEERING")
    assert code == "CHEM"

    # Test 5: Civil
    code, name = identify_department("B.E 2025 SCHEME - CIVIL ENGINEERING")
    assert code == "CIVIL"

    # Test 10: Unknown Program
    with pytest.raises(ValidationError):
        # Passing an unknown program through DataImporter should raise a ValidationError
        # Verify through import_excel
        rows = [{"SIN": "ERR123", "STUDENT FULL NAME": "Error Student", "PROGRAM": "B.E 2025 SCHEME - SOME UNKNOWN BRANCH"}]
        df = pd.DataFrame(rows)
        temp_csv = Path("data/temp_test_error.csv")
        df.to_csv(temp_csv, index=False)
        mapping = {"SIN": "sin", "STUDENT FULL NAME": "full_name", "PROGRAM": "program"}
        try:
            DataImporter.import_excel(temp_csv, mapping)
        finally:
            if temp_csv.exists():
                temp_csv.unlink()

def test_student_identity_and_import_scenarios():
    session = SessionLocal()
    try:
        # Create a temp csv file for importing
        rows = [
            {"SIN": "ABC123", "STUDENT FULL NAME": "Rahul Kumar", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE", "GENDER": "Male"}
        ]
        df = pd.DataFrame(rows)
        temp_csv = Path("data/temp_test_import_identity.csv")
        df.to_csv(temp_csv, index=False)
        
        mapping = {"SIN": "sin", "STUDENT FULL NAME": "full_name", "PROGRAM": "program", "GENDER": "gender"}
        
        # Test 6: Import first student
        res1 = DataImporter.import_excel(temp_csv, mapping)
        assert res1["success"] is True
        assert res1["new_students"] == 1
        
        # Test 6 (cont): Re-importing exact same SIN should update it (treated as same student)
        # Update name in same file
        rows[0]["STUDENT FULL NAME"] = "Rahul Kumar Updated"
        df2 = pd.DataFrame(rows)
        # We need a different file content/hash so it's not marked as duplicate upload
        df2.to_csv(temp_csv, index=False)
        
        res2 = DataImporter.import_excel(temp_csv, mapping)
        assert res2["success"] is True
        assert res2["updated_students"] == 1
        
        session.expire_all()
        stu = session.query(Student).filter(Student.usn == "ABC123").first()
        assert stu.full_name == "Rahul Kumar Updated"

        # Test 7: Different SIN, Same Name
        rows_diff = [
            {"SIN": "XYZ456", "STUDENT FULL NAME": "Rahul Kumar Updated", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE", "GENDER": "Male"}
        ]
        df_diff = pd.DataFrame(rows_diff)
        df_diff.to_csv(temp_csv, index=False)
        res3 = DataImporter.import_excel(temp_csv, mapping)
        assert res3["success"] is True
        assert res3["new_students"] == 1
        
        session.expire_all()
        # Verify both exist
        count = session.query(Student).filter(Student.full_name == "Rahul Kumar Updated").count()
        assert count == 2

        # Test 8: Similar SIN (ABC123 vs ABC124)
        rows_sim = [
            {"SIN": "ABC124", "STUDENT FULL NAME": "Rahul Kumar Updated", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE", "GENDER": "Male"}
        ]
        df_sim = pd.DataFrame(rows_sim)
        df_sim.to_csv(temp_csv, index=False)
        res4 = DataImporter.import_excel(temp_csv, mapping)
        assert res4["success"] is True
        assert res4["new_students"] == 1
        
        # Test 9: Typo in name with exact SIN match
        rows_typo = [
            {"SIN": "ABC123", "STUDENT FULL NAME": "Rahul Kumr", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE", "GENDER": "Male"}
        ]
        df_typo = pd.DataFrame(rows_typo)
        df_typo.to_csv(temp_csv, index=False)
        res5 = DataImporter.import_excel(temp_csv, mapping)
        assert res5["success"] is True
        assert res5["updated_students"] == 1
        
        session.expire_all()
        stu_typo = session.query(Student).filter(Student.usn == "ABC123").first()
        assert stu_typo.full_name == "Rahul Kumr"

        # Test 11: Gender Column Missing
        rows_no_gender = [
            {"SIN": "DEF789", "STUDENT FULL NAME": "No Gender Student", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE"}
        ]
        df_no_gender = pd.DataFrame(rows_no_gender)
        df_no_gender.to_csv(temp_csv, index=False)
        mapping_no_gender = {"SIN": "sin", "STUDENT FULL NAME": "full_name", "PROGRAM": "program"}
        res6 = DataImporter.import_excel(temp_csv, mapping_no_gender)
        assert res6["success"] is True
        assert res6["new_students"] == 1
        
        session.expire_all()
        stu_no_gender = session.query(Student).filter(Student.usn == "DEF789").first()
        assert stu_no_gender.gender == "Unknown"

        # Test 12: Gender Column Present
        rows_gender = [
            {"SIN": "GHI012", "STUDENT FULL NAME": "Gender Student", "PROGRAM": "B.E 2025 SCHEME - COMPUTER SCIENCE", "GENDER": "Female"}
        ]
        df_gender = pd.DataFrame(rows_gender)
        df_gender.to_csv(temp_csv, index=False)
        res7 = DataImporter.import_excel(temp_csv, mapping)
        assert res7["success"] is True
        assert res7["new_students"] == 1
        
        session.expire_all()
        stu_gender = session.query(Student).filter(Student.usn == "GHI012").first()
        assert stu_gender.gender == "Female"

        # Clean up
        if temp_csv.exists():
            temp_csv.unlink()

    finally:
        session.close()
