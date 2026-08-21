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

def test_user_requested_department_tests_1_to_5():
    # Test 1: ETE
    code1, name1 = identify_department("B.E 2025 SCHEME -   ELECTRONICS & TELE ENG")
    assert code1 == "ETE"
    assert name1 == "Electronics & Telecommunication Engineering"

    # Test 2: IEM
    code2, name2 = identify_department("B.E 2025 SCHEME -   INDUSTRIAL ENGG & MNGT")
    assert code2 == "IEM"
    assert name2 == "Industrial Engineering & Management"

    # Test 3: AS
    code3, name3 = identify_department("B.E 2025 SCHEME -   AEROSPACE")
    assert code3 == "AS"
    assert name3 == "Aerospace Engineering"

    # Test 4: ECE (Must NOT be identified as ETE)
    code4, name4 = identify_department("B.E 2025 SCHEME -   ELECTRONICS & COMM")
    assert code4 == "ECE"
    assert code4 != "ETE"
    assert name4 == "Electronics & Communication Engineering"

    # Test 5: IEM (Must NOT be identified as MECH or CSE)
    code5, name5 = identify_department("B.E 2025 SCHEME -   INDUSTRIAL ENGG & MNGT")
    assert code5 == "IEM"
    assert code5 not in ["MECH", "CSE"]
    assert name5 == "Industrial Engineering & Management"

def test_mixed_import_all_13_supported_departments():
    session = SessionLocal()
    try:
        sample_departments = [
            ("1RV26CS001", "Student CSE", "B.E 2025 SCHEME - COMPUTER SCIENCE", "CSE", "Computer Science Engineering"),
            ("1RV26AI001", "Student AIML", "B.E 2025 SCHEME - CSE(AI&ML)", "AIML", "Artificial Intelligence & Machine Learning"),
            ("1RV26CY001", "Student CY", "B.E 2025 SCHEME - CYBER SECURITY", "CY", "Cyber Security"),
            ("1RV26DS001", "Student DS", "B.E 2025 SCHEME - DATA SCIENCE", "DS", "Data Science"),
            ("1RV26EC001", "Student ECE", "B.E 2025 SCHEME -   ELECTRONICS & COMM", "ECE", "Electronics & Communication Engineering"),
            ("1RV26ET001", "Student ETE", "B.E 2025 SCHEME -   ELECTRONICS & TELE ENG", "ETE", "Electronics & Telecommunication Engineering"),
            ("1RV26EE001", "Student EEE", "B.E 2025 SCHEME - ELECTRICAL & ELECTRONICS", "EEE", "Electrical & Electronics Engineering"),
            ("1RV26ME001", "Student MECH", "B.E 2025 SCHEME - MECHANICAL ENGINEERING", "MECH", "Mechanical Engineering"),
            ("1RV26CH001", "Student CHEM", "B.E 2025 SCHEME - CHEMICAL ENGINEERING", "CHEM", "Chemical Engineering"),
            ("1RV26CV001", "Student CIVIL", "B.E 2025 SCHEME - CIVIL ENGINEERING", "CIVIL", "Civil Engineering"),
            ("1RV26BT001", "Student BT", "B.E 2025 SCHEME - BIOTECHNOLOGY", "BT", "Biotechnology"),
            ("1RV26IM001", "Student IEM", "B.E 2025 SCHEME -   INDUSTRIAL ENGG & MNGT", "IEM", "Industrial Engineering & Management"),
            ("1RV26AS001", "Student AS", "B.E 2025 SCHEME -   AEROSPACE", "AS", "Aerospace Engineering"),
        ]

        rows = []
        for sin, name, prog, _, _ in sample_departments:
            rows.append({
                "SIN": sin,
                "STUDENT FULL NAME": name,
                "PROGRAM": prog,
                "GENDER": "Male"
            })

        df = pd.DataFrame(rows)
        temp_csv = Path("data/temp_test_all_13_depts.csv")
        df.to_csv(temp_csv, index=False)

        mapping = {"SIN": "sin", "STUDENT FULL NAME": "full_name", "PROGRAM": "program", "GENDER": "gender"}
        
        try:
            res = DataImporter.import_excel(temp_csv, mapping)
            assert res["success"] is True
            assert res["new_students"] == 13
            assert res["unknown_departments"] == 0

            # Verify in DB that each student got the exact department code and name
            session.expire_all()
            for sin, _, _, expected_code, expected_name in sample_departments:
                stu = session.query(Student).filter(Student.usn == sin).first()
                assert stu is not None, f"Student {sin} not found in DB"
                assert stu.department.code == expected_code, f"Expected code {expected_code} for {sin}, got {stu.department.code}"
                assert stu.department.name == expected_name, f"Expected name {expected_name} for {sin}, got {stu.department.name}"
        finally:
            if temp_csv.exists():
                temp_csv.unlink()
    finally:
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
