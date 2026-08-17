import pandas as pd
import hashlib
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
            for req in ['student_id', 'full_name', 'department']:
                if req not in df_renamed.columns:
                    raise ValidationError(f"Required field '{req}' is missing in column mapping.")

            new_count = 0
            updated_count = 0
            duplicate_usn_count = 0
            warnings = []

            # Pre-load existing students map
            existing_students_map = {
                s.usn.strip().upper(): s for s in session.query(Student).filter(Student.is_deleted == False).all()
            }
            existing_names_list = [(s.full_name, s.usn) for s in existing_students_map.values()]

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
                raw_stu_id = str(row['student_id']).strip() if pd.notna(row['student_id']) else ""
                raw_usn = raw_stu_id
                raw_name = str(row['full_name']).strip() if pd.notna(row['full_name']) else ""
                raw_dept = str(row['department']).strip() if pd.notna(row['department']) else ""
                raw_prog = str(row.get('program', 'B.Tech')).strip() if pd.notna(row.get('program')) else "B.Tech"
                raw_gender = str(row.get('gender', 'Unknown')) if pd.notna(row.get('gender')) else "Unknown"
                raw_stu_num = str(row.get('student_number', '')).strip() if pd.notna(row.get('student_number')) else None

                if not raw_stu_id or raw_stu_id.lower() in ['nan', 'none', 'null']:
                    warnings.append(f"Row {row_num}: Skipped record due to blank Student ID.")
                    continue
                if not raw_name or raw_name.lower() in ['nan', 'none', 'null']:
                    warnings.append(f"Row {row_num} (Student ID: {raw_stu_id}): Skipped record due to blank name.")
                    continue
                if not raw_dept or raw_dept.lower() in ['nan', 'none', 'null']:
                    warnings.append(f"Row {row_num} (Student ID: {raw_stu_id}): Skipped record due to blank department.")
                    continue

                clean_usn_key = raw_usn.upper()
                gender_enum = Gender.parse(raw_gender)

                # Extract branch code from USN (e.g. "CE" or "CV" from "1RV26CE001")
                usn_branch_code = None
                if len(clean_usn_key) >= 7:
                    potential_branch = clean_usn_key[5:7]
                    if potential_branch.isalpha():
                        usn_branch_code = potential_branch

                CANONICAL_DEPARTMENTS = {
                    "CS": "Computer Science Engineering",
                    "AI": "Artificial Intelligence & Machine Learning",
                    "DS": "Data Science",
                    "CY": "Cyber Security",
                    "EC": "Electronics & Communication Engineering",
                    "ET": "Electronics & Telecommunication Engineering",
                    "EE": "Electrical & Electronics Engineering",
                    "CE": "Chemical Engineering",
                    "ME": "Mechanical Engineering",
                    "IM": "Industrial Engineering & Management",
                    "CV": "Civil Engineering",
                    "BT": "Biotechnology"
                }

                if usn_branch_code in CANONICAL_DEPARTMENTS:
                    resolved_dept_name = CANONICAL_DEPARTMENTS[usn_branch_code]
                    resolved_dept_code = usn_branch_code
                else:
                    resolved_dept_name = raw_dept
                    resolved_dept_code = None

                dept_obj = Repository.get_or_create_department(session, resolved_dept_name, resolved_dept_code)
                prog_obj = Repository.get_or_create_program(session, raw_prog)

                # Check if Student ID (mapped to USN) exists in DB
                if clean_usn_key in existing_students_map:
                    stu = existing_students_map[clean_usn_key]
                    if stu.import_history_id is None:
                        stu.import_history_id = imp_record.id
                    
                    # Update fields if faculty corrected typo, preserving allocation!
                    changed = False
                    if stu.full_name != raw_name:
                        warnings.append(f"Student ID {raw_stu_id}: Updated name from '{stu.full_name}' to '{raw_name}'.")
                        stu.full_name = raw_name
                        changed = True
                    if stu.department_id != dept_obj.id:
                        warnings.append(f"Student ID {raw_stu_id}: Updated department to '{dept_obj.name}'. Existing allocations preserved.")
                        stu.department_id = dept_obj.id
                        changed = True
                    if stu.gender != gender_enum.value:
                        stu.gender = gender_enum.value
                        changed = True

                    # Reactivate if inactive
                    if stu.status == StudentStatus.INACTIVE.value:
                        stu.status = StudentStatus.ACTIVE.value
                        warnings.append(f"Student ID {raw_stu_id}: Reactivated student status to Active.")
                        changed = True

                    if changed:
                        updated_count += 1
                    else:
                        duplicate_usn_count += 1
                else:
                    # Near duplicate name check
                    for existing_name, ex_usn in existing_names_list:
                        similarity = fuzz.token_sort_ratio(raw_name.lower(), existing_name.lower())
                        if similarity >= NEAR_DUPLICATE_THRESHOLD:
                            warnings.append(f"Row {row_num}: Near-duplicate name warning! '{raw_name}' (Student ID: {raw_stu_id}) is {similarity}% similar to existing student '{existing_name}' (Student ID: {ex_usn}).")
                            break

                    new_stu = Student(
                        usn=raw_usn,
                        student_id=raw_stu_id,
                        student_number=raw_stu_num,
                        full_name=raw_name,
                        gender=gender_enum.value,
                        status=StudentStatus.ACTIVE.value,
                        department_id=dept_obj.id,
                        program_id=prog_obj.id,
                        import_history_id=imp_record.id,
                        created_at=datetime.utcnow()
                    )
                    session.add(new_stu)
                    existing_students_map[clean_usn_key] = new_stu
                    existing_names_list.append((raw_name, raw_usn))
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
                "warnings": warnings,
                "is_reimport": existing_import is not None
            }

        except Exception as e:
            session.rollback()
            raise ValidationError(f"Import process failed: {str(e)}")
        finally:
            session.close()
