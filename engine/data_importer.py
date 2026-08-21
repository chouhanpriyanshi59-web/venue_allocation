import pandas as pd
import hashlib
import re
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
from pathlib import Path
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Student, Department, Program, ImportHistory, AuditLog
from database.repository import Repository
from engine.column_mapper import ColumnMapper
from core.domain_models import Gender, StudentStatus
from core.exceptions import ValidationError, InductionSystemError
from config import NEAR_DUPLICATE_THRESHOLD

def normalize_program_text(text: str) -> str:
    """Normalizes the program text for uniform matching."""
    text = text.upper().strip()
    text = text.replace(".", "")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("&", "AND")
    text = " ".join(text.split())
    return text

def identify_department(program_text: str) -> Tuple[str, str]:
    """
    Identifies the department code and name from the program text.
    Returns (code, name) if found, else raises ValueError.
    """
    norm = normalize_program_text(program_text)
    
    # Priority order rules to prevent overlapping patterns
    rules = [
        ("AIML", "Artificial Intelligence & Machine Learning", r"ARTIFICIAL INTELLIGENCE|\bAIANDML\b|AI\&ML|\bAIML\b|\bAI\b"),
        ("CY", "Cyber Security", r"CYBER SECURITY|\bCYBER\b|\bCY\b"),
        ("DS", "Data Science", r"DATA SCIENCE|\bDS\b"),
        ("ETE", "Electronics & Telecommunication Engineering", r"TELECOMMUNICATION|TELECOMM|TELE ENG|\bTELE\b|\bETE\b|\bET\b"),
        ("ECE", "Electronics & Communication Engineering", r"ELECTRONICS AND COMMUNICATION|ELECTRONICS AND COMM|ELECTRONICS \& COMM|\bECE\b|\bEC\b"),
        ("EEE", "Electrical & Electronics Engineering", r"ELECTRICAL AND ELECTRONICS|ELECTRICAL \& ELECTRONICS|\bEEE\b|\bEE\b"),
        ("CHEM", "Chemical Engineering", r"CHEMICAL|\bCHEM\b|\bCE\b"),
        ("CIVIL", "Civil Engineering", r"CIVIL|\bCV\b"),
        ("BT", "Biotechnology", r"BIOTECHNOLOGY|BIOTECH|\bBT\b"),
        ("IEM", "Industrial Engineering & Management", r"INDUSTRIAL ENGINEERING|INDUSTRIAL ENGG|INDUSTRIAL ENG|\bINDUSTRIAL\b|\bIEM\b|\bIM\b"),
        ("MECH", "Mechanical Engineering", r"MECHANICAL|\bMECH\b|\bME\b"),
        ("AS", "Aerospace Engineering", r"AEROSPACE|\bAS\b"),
        ("CSE", "Computer Science Engineering", r"COMPUTER SCIENCE|COMPUTER SCIENCE ENGINEERING|\bCSE\b|\bCS\b"),
    ]
    
    for code, name, pattern in rules:
        if re.search(pattern, norm):
            return code, name
            
    raise ValueError(f"Unable to identify department for program: {program_text}")

class DataImporter:
    """Handles file parsing, fuzzy header mapping, validation, duplicate detection, and smart differential imports."""

    @classmethod
    def inspect_file(cls, file_path: Path) -> Tuple[Dict[str, str], List[str], List[str], int]:
        """Reads file headers and returns proposed column mappings and row count."""
        ext = file_path.suffix.lower()
        if ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, nrows=5)
        elif ext == '.csv':
            df = pd.read_csv(file_path, nrows=5)
        else:
            raise ValidationError(f"Unsupported file format: {ext}. Please upload .xlsx, .xls, or .csv")

        total_rows = len(pd.read_excel(file_path)) if ext in ['.xlsx', '.xls'] else len(pd.read_csv(file_path))

        mapping, unmapped, missing_required = ColumnMapper.map_columns(list(df.columns))
        return mapping, unmapped, missing_required, total_rows

    @classmethod
    def import_excel(cls, file_path: Path, column_mapping: Dict[str, str]) -> Dict[str, Any]:
        """Executes the full import pipeline with validation, diffing, and audit logging."""
        ext = file_path.suffix.lower()
        if ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        elif ext == '.csv':
            df = pd.read_csv(file_path)
        else:
            raise ValidationError(f"Unsupported file format: {ext}")

        # Hash file to detect re-uploading identical file
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        session: Session = SessionLocal()
        try:
            # Check duplicate upload
            existing_import = session.query(ImportHistory).filter(ImportHistory.file_hash == file_hash).first()
            
            # Map columns in DataFrame
            df_renamed = df.rename(columns=column_mapping)
            
            # Verify required columns exist
            for req in ['sin', 'full_name', 'program']:
                if req not in df_renamed.columns:
                    raise ValidationError(f"Required field '{req}' is missing in column mapping.")

            new_count = 0
            updated_count = 0
            duplicate_usn_count = 0
            warnings = []

            # Pre-load existing students map (case-sensitive exact SIN matching)
            existing_students_map = {
                s.usn.strip(): s for s in session.query(Student).filter(Student.is_deleted == False).all()
            }

            # Create ImportHistory record first
            imp_record = ImportHistory(
                file_name=file_path.name,
                file_hash=file_hash,
                total_rows=len(df),
                new_records=0,
                updated_records=0,
                duplicate_records=0,
                imported_at=datetime.utcnow()
            )
            session.add(imp_record)
            session.flush()

            for idx, row in df_renamed.iterrows():
                row_num = idx + 2  # Excel 1-based header offset
                raw_sin = str(row['sin']).strip() if pd.notna(row['sin']) else ""
                raw_name = str(row['full_name']).strip() if pd.notna(row['full_name']) else ""
                raw_prog = str(row['program']).strip() if pd.notna(row['program']) else ""

                if not raw_sin or raw_sin.lower() in ['nan', 'none', 'null']:
                    raise ValidationError(f"Row {row_num}: SIN is required and cannot be empty.")
                if not raw_name or raw_name.lower() in ['nan', 'none', 'null']:
                    raise ValidationError(f"Row {row_num}: Student Full Name is required and cannot be empty.")
                if not raw_prog or raw_prog.lower() in ['nan', 'none', 'null']:
                    raise ValidationError(f"Row {row_num}: Program is required and cannot be empty.")

                clean_sin = raw_sin.strip()

                # GENDER is optional
                if 'gender' in row and pd.notna(row['gender']):
                    raw_gender = str(row['gender']).strip()
                    gender_enum = Gender.parse(raw_gender)
                else:
                    gender_enum = Gender.UNKNOWN

                # Extract department information from PROGRAM
                try:
                    dept_code, dept_name = identify_department(raw_prog)
                except ValueError:
                    raise ValidationError(
                        f"Unable to identify department for program:\n"
                        f"{raw_prog} at row {row_num} (Student Name: '{raw_name}', SIN: '{raw_sin}')."
                    )

                dept_obj = Repository.get_or_create_department(session, dept_name, dept_code)
                prog_obj = Repository.get_or_create_program(session, raw_prog)

                # Check if exact case-sensitive SIN exists in DB
                if clean_sin in existing_students_map:
                    stu = existing_students_map[clean_sin]
                    if stu.import_history_id is None:
                        stu.import_history_id = imp_record.id
                    
                    changed = False
                    if stu.full_name != raw_name:
                        warnings.append(f"SIN {raw_sin}: Updated name from '{stu.full_name}' to '{raw_name}'.")
                        stu.full_name = raw_name
                        changed = True
                    if stu.department_id != dept_obj.id:
                        warnings.append(f"SIN {raw_sin}: Updated department to '{dept_obj.name}'. Existing allocations preserved.")
                        stu.department_id = dept_obj.id
                        changed = True
                    if stu.program_id != prog_obj.id:
                        stu.program_id = prog_obj.id
                        changed = True
                    # Only update/validate gender if the GENDER column was actually provided
                    if 'gender' in row and pd.notna(row['gender']):
                        if stu.gender != gender_enum.value:
                            stu.gender = gender_enum.value
                            changed = True

                    # Reactivate if inactive
                    if stu.status == StudentStatus.INACTIVE.value:
                        stu.status = StudentStatus.ACTIVE.value
                        warnings.append(f"SIN {raw_sin}: Reactivated student status to Active.")
                        changed = True

                    if changed:
                        updated_count += 1
                    else:
                        duplicate_usn_count += 1
                else:
                    new_stu = Student(
                        usn=clean_sin,
                        student_id=clean_sin,
                        student_number=None,
                        full_name=raw_name,
                        gender=gender_enum.value,
                        status=StudentStatus.ACTIVE.value,
                        department_id=dept_obj.id,
                        program_id=prog_obj.id,
                        import_history_id=imp_record.id,
                        created_at=datetime.utcnow()
                    )
                    session.add(new_stu)
                    existing_students_map[clean_sin] = new_stu
                    new_count += 1

            # Update final counts on ImportHistory
            imp_record.new_records = new_count
            imp_record.updated_records = updated_count
            imp_record.duplicate_records = duplicate_usn_count

            # Audit Log
            audit = AuditLog(
                action="EXCEL_IMPORT_SUCCESS",
                entity_type="Student",
                details=f"Imported file '{file_path.name}': {new_count} new students, {updated_count} updated, {duplicate_usn_count} duplicates/skipped."
            )
            session.add(audit)

            session.commit()

            return {
                "success": True,
                "file_name": file_path.name,
                "total_rows": len(df),
                "new_students": new_count,
                "updated_students": updated_count,
                "duplicate_skipped": duplicate_usn_count,
                "invalid_rows": 0,
                "unknown_departments": 0,
                "warnings": warnings,
                "is_reimport": existing_import is not None
            }

        except Exception as e:
            session.rollback()
            raise ValidationError(f"Import process failed: {str(e)}")
        finally:
            session.close()
