from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from database.connection import SessionLocal
from database.models import (
    Student, Department, Program, Venue, TimeSlot,
    ImportHistory, AuditLog, AppSettings, AllocationRun
)
from core.domain_models import StudentRecord, Gender, StudentStatus

class Repository:
    """Encapsulates all database query and transaction logic."""

    @staticmethod
    def get_or_create_department(session: Session, name: str, code: Optional[str] = None) -> Department:
        clean_name = name.strip()
        
        # Standardize mappings
        NAME_TO_CODE = {
            "civil engineering": "CV",
            "chemical engineering": "CE",
            "computer science engineering": "CS",
            "computer science & engineering": "CS",
            "computer science": "CS",
            "cyber security": "CY",
            "biotechnology": "BT",
            "electrical & electronics engineering": "EE",
            "electrical and electronics engineering": "EE",
            "electronics & communication engineering": "EC",
            "electronics and communication engineering": "EC",
            "electronics & telecommunication engineering": "ET",
            "electronics and telecommunication engineering": "ET",
            "industrial engineering & management": "IM",
            "industrial engineering and management": "IM",
            "mechanical engineering": "ME",
            "data science": "DS",
            "artificial intelligence & machine learning": "AI",
            "artificial intelligence and machine learning": "AI"
        }
        
        CODE_TO_NAME = {
            "CS": "Computer Science Engineering",
            "CSE": "Computer Science Engineering",
            "AI": "Artificial Intelligence & Machine Learning",
            "AIML": "Artificial Intelligence & Machine Learning",
            "DS": "Data Science",
            "CY": "Cyber Security",
            "EC": "Electronics & Communication Engineering",
            "ECE": "Electronics & Communication Engineering",
            "ET": "Electronics & Telecommunication Engineering",
            "ETE": "Electronics & Telecommunication Engineering",
            "EE": "Electrical & Electronics Engineering",
            "EEE": "Electrical & Electronics Engineering",
            "CE": "Chemical Engineering",
            "ME": "Mechanical Engineering",
            "IM": "Industrial Engineering & Management",
            "IEM": "Industrial Engineering & Management",
            "CV": "Civil Engineering",
            "BT": "Biotechnology"
        }

        # Determine target name and code
        derived_code = None
        target_name = clean_name
        
        # 1. Resolve canonical name if clean_name matches a key in NAME_TO_CODE
        norm_name_lower = clean_name.lower()
        if norm_name_lower in NAME_TO_CODE:
            derived_code = NAME_TO_CODE[norm_name_lower]
            target_name = CODE_TO_NAME[derived_code]
            
        # 2. Check if clean_name is actually a code (e.g., "CE", "CV", "CSE")
        norm_name_upper = clean_name.upper()
        if not derived_code and norm_name_upper in CODE_TO_NAME:
            derived_code = norm_name_upper
            target_name = CODE_TO_NAME[norm_name_upper]

        # 3. If code is explicitly provided, override derived_code and potentially resolve name
        if code:
            code_upper = code.strip().upper()
            derived_code = code_upper
            if code_upper in CODE_TO_NAME and (not clean_name or clean_name.lower() in [c.lower() for c in CODE_TO_NAME.values()] or clean_name.upper() in CODE_TO_NAME):
                target_name = CODE_TO_NAME[code_upper]

        # 4. Fallback if still not resolved
        if not derived_code:
            dept_code = clean_name.upper()[:20]
            if len(dept_code) > 4 and " " in clean_name:
                words = [w for w in clean_name.replace("&", "").split() if w]
                if len(words) >= 2:
                    derived_code = "".join([w[0] for w in words]).upper()[:10]
                else:
                    derived_code = clean_name[:4].upper()
            else:
                derived_code = dept_code

        # Search database strictly matching code OR name (case-insensitive)
        dept = session.query(Department).filter(
            or_(
                func.lower(Department.code) == derived_code.lower(),
                func.lower(Department.name) == target_name.lower()
            )
        ).first()

        if not dept:
            # Ensure unique derived_code
            base_code = derived_code
            counter = 1
            while session.query(Department).filter(func.lower(Department.code) == derived_code.lower()).first():
                derived_code = f"{base_code[:15]}{counter}"
                counter += 1

            dept = Department(name=target_name, code=derived_code)
            session.add(dept)
            session.flush()

        return dept

    @staticmethod
    def get_or_create_program(session: Session, name: str, code: Optional[str] = None) -> Program:
        clean_name = name.strip()
        prog_code = (code or clean_name).strip().upper()[:20]
        if len(prog_code) > 4 and not code and " " in clean_name:
            words = [w for w in clean_name.replace("&", "").split() if w]
            if len(words) >= 2:
                derived_code = "".join([w[0] for w in words]).upper()[:10]
            else:
                derived_code = clean_name[:4].upper()
        else:
            derived_code = prog_code

        # 1. Search for existing program matching code OR name (case-insensitive)
        prog = session.query(Program).filter(
            or_(
                func.lower(Program.code) == derived_code.lower(),
                func.lower(Program.code) == clean_name.lower(),
                func.lower(Program.name) == clean_name.lower()
            )
        ).first()

        if not prog:
            # 2. Ensure derived_code is strictly unique among existing codes
            base_code = derived_code
            counter = 1
            while session.query(Program).filter(func.lower(Program.code) == derived_code.lower()).first():
                derived_code = f"{base_code[:15]}{counter}"
                counter += 1

            prog = Program(name=clean_name, code=derived_code)
            session.add(prog)
            session.flush()

        return prog

    @staticmethod
    def get_or_create_venue(session: Session, name: str, capacity: int, location: Optional[str] = None, group_name: Optional[str] = None) -> Venue:
        clean_name = name.strip()
        query = session.query(Venue).filter(func.lower(Venue.name) == clean_name.lower())
        if group_name:
            query = query.filter(Venue.group_name == group_name)
        else:
            query = query.filter(Venue.group_name.is_(None))
        venue = query.first()
        if not venue:
            venue = Venue(name=clean_name, capacity=capacity, location=location, group_name=group_name)
            session.add(venue)
            session.flush()
        else:
            if capacity != venue.capacity:
                venue.capacity = capacity
                session.flush()
        return venue

    @staticmethod
    def get_or_create_time_slot(session: Session, slot_name: str, start_time: str, end_time: str, day_number: int = 1, group_name: Optional[str] = None) -> TimeSlot:
        clean_slot = slot_name.strip()
        query = session.query(TimeSlot).filter(
            func.lower(TimeSlot.slot_name) == clean_slot.lower(),
            TimeSlot.day_number == day_number
        )
        if group_name:
            query = query.filter(TimeSlot.group_name == group_name)
        else:
            query = query.filter(TimeSlot.group_name.is_(None))
        ts = query.first()
        if not ts:
            ts = TimeSlot(slot_name=clean_slot, start_time=start_time, end_time=end_time, day_number=day_number, group_name=group_name)
            session.add(ts)
            session.flush()
        return ts

    @classmethod
    def get_students(
        cls,
        session: Session,
        search_query: Optional[str] = None,
        department_id: Optional[int] = None,
        program_id: Optional[int] = None,
        group_name: Optional[str] = None,
        venue_id: Optional[int] = None,
        time_slot_id: Optional[int] = None,
        gender: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> Tuple[List[Student], int]:
        """Queries students with filters, full text search across USN/ID/Name, and pagination."""
        query = session.query(Student).options(
            joinedload(Student.department),
            joinedload(Student.program),
            joinedload(Student.venue),
            joinedload(Student.time_slot)
        ).filter(Student.is_deleted == False)

        if search_query and search_query.strip():
            term = f"%{search_query.strip()}%"
            query = query.filter(
                or_(
                    Student.usn.ilike(term),
                    Student.student_id.ilike(term),
                    Student.student_number.ilike(term),
                    Student.full_name.ilike(term)
                )
            )

        if department_id:
            query = query.filter(Student.department_id == department_id)
        if program_id:
            query = query.filter(Student.program_id == program_id)
        if group_name:
            query = query.filter(Student.group_name == group_name)
        if venue_id:
            query = query.filter(Student.venue_id == venue_id)
        if time_slot_id:
            query = query.filter(Student.time_slot_id == time_slot_id)
        if gender and gender != "All":
            query = query.filter(Student.gender == gender)
        if status and status != "All":
            query = query.filter(Student.status == status)

        total_count = query.count()

        query = query.order_by(Student.usn.asc())

        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return query.all(), total_count

    @classmethod
    def get_dashboard_summary(cls, session: Session) -> Dict[str, Any]:
        """Generates summary statistics for the dashboard cards and charts."""
        total_students = session.query(Student).filter(Student.is_deleted == False).count()
        allocated_groups = session.query(Student).filter(Student.is_deleted == False, Student.group_name.isnot(None)).count()
        allocated_venues = session.query(Student).filter(Student.is_deleted == False, Student.venue_id.isnot(None)).count()
        pending_allocation = session.query(Student).filter(Student.is_deleted == False, Student.group_name.is_(None)).count()

        group_counts = session.query(
            Student.group_name, func.count(Student.id)
        ).filter(Student.is_deleted == False).group_by(Student.group_name).all()

        gender_counts = session.query(
            Student.gender, func.count(Student.id)
        ).filter(Student.is_deleted == False).group_by(Student.gender).all()

        dept_counts = session.query(
            Department.name, func.count(Student.id)
        ).join(Student, Student.department_id == Department.id).filter(
            Student.is_deleted == False
        ).group_by(Department.name).all()

        venues = session.query(Venue).filter(Venue.is_active == True).all()
        venue_stats = []
        for v in venues:
            filled = session.query(Student).filter(Student.venue_id == v.id, Student.is_deleted == False).count()
            venue_stats.append({
                "id": v.id,
                "name": v.name,
                "capacity": v.capacity,
                "filled": filled,
                "remaining": max(0, v.capacity - filled)
            })

        recent_imports = session.query(ImportHistory).order_by(ImportHistory.imported_at.desc()).limit(10).all()

        return {
            "total_students": total_students,
            "allocated_groups": allocated_groups,
            "allocated_venues": allocated_venues,
            "pending_allocation": pending_allocation,
            "group_distribution": {g or "Unassigned": cnt for g, cnt in group_counts},
            "gender_distribution": {gen or "Unknown": cnt for gen, cnt in gender_counts},
            "department_distribution": {d: cnt for d, cnt in dept_counts},
            "venue_utilization": venue_stats,
            "recent_imports": recent_imports
        }

    @classmethod
    def delete_import_history(cls, session: Session, import_id: int) -> Tuple[bool, str]:
        """Deletes an import history record and removes all associated students from SQLite."""
        imp = session.query(ImportHistory).filter(ImportHistory.id == import_id).first()
        if not imp:
            return False, "Import record not found."

        file_name = imp.file_name

        # 1. Find associated students by import_history_id
        students = session.query(Student).filter(Student.import_history_id == import_id).all()

        # 2. Smart fallback for legacy imports where import_history_id was None
        if not students:
            all_imports_count = session.query(ImportHistory).count()
            if all_imports_count == 1:
                # If only 1 import record exists, all non-deleted students belong to this import
                students = session.query(Student).all()
            else:
                from datetime import timedelta
                start_time = imp.imported_at - timedelta(seconds=120)
                end_time = imp.imported_at + timedelta(seconds=120)
                students = session.query(Student).filter(
                    Student.created_at >= start_time,
                    Student.created_at <= end_time
                ).all()

        deleted_student_count = len(students)

        # Delete student records
        for s in students:
            session.delete(s)

        # Delete import history record
        session.delete(imp)

        audit = AuditLog(
            action="IMPORT_FILE_DELETED",
            entity_type="ImportHistory",
            entity_id=str(import_id),
            details=f"Deleted import file record '{file_name}' and removed {deleted_student_count} associated students."
        )
        session.add(audit)
        session.commit()
        return True, f"Successfully deleted import file '{file_name}' and removed {deleted_student_count} associated students."


    @classmethod
    def delete_venue(cls, session: Session, venue_id: int) -> Tuple[bool, str]:
        """Deletes a venue record and resets venue assignments for any affected students."""
        venue = session.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return False, "Venue not found."

        name = venue.name
        session.query(Student).filter(Student.venue_id == venue_id).update(
            {Student.venue_id: None, Student.venue_allocated_at: None},
            synchronize_session=False
        )
        session.query(Student).filter(Student.group_venue_id == venue_id).update(
            {Student.group_venue_id: None, Student.group_venue_allocated_at: None},
            synchronize_session=False
        )
        session.query(Student).filter(Student.branch_venue_id == venue_id).update(
            {Student.branch_venue_id: None, Student.branch_venue_allocated_at: None},
            synchronize_session=False
        )
        session.delete(venue)

        audit = AuditLog(
            action="VENUE_DELETED",
            entity_type="Venue",
            entity_id=str(venue_id),
            details=f"Deleted venue '{name}' (ID {venue_id}) and reset venue assignments for affected students."
        )
        session.add(audit)
        session.commit()
        return True, f"Successfully deleted venue '{name}'."

    @classmethod
    def delete_time_slot(cls, session: Session, time_slot_id: int) -> Tuple[bool, str]:
        """Deletes a time slot record and resets time slot assignments for any affected students."""
        ts = session.query(TimeSlot).filter(TimeSlot.id == time_slot_id).first()
        if not ts:
            return False, "Time slot not found."

        slot_name = ts.slot_name
        session.query(Student).filter(Student.time_slot_id == time_slot_id).update(
            {Student.time_slot_id: None, Student.venue_allocated_at: None},
            synchronize_session=False
        )
        session.query(Student).filter(Student.group_time_slot_id == time_slot_id).update(
            {Student.group_time_slot_id: None, Student.group_venue_allocated_at: None},
            synchronize_session=False
        )
        session.query(Student).filter(Student.branch_time_slot_id == time_slot_id).update(
            {Student.branch_time_slot_id: None, Student.branch_venue_allocated_at: None},
            synchronize_session=False
        )
        session.delete(ts)

        audit = AuditLog(
            action="TIMESLOT_DELETED",
            entity_type="TimeSlot",
            entity_id=str(time_slot_id),
            details=f"Deleted time slot '{slot_name}' (ID {time_slot_id}) and reset time slot assignments for affected students."
        )
        session.add(audit)
        session.commit()
        return True, f"Successfully deleted time slot '{slot_name}'."

    @classmethod
    def get_allocation_runs(cls, session: Session, mode: Optional[str] = None) -> List[AllocationRun]:
        """Retrieves historical allocation runs, optionally filtered by mode."""
        query = session.query(AllocationRun)
        if mode:
            query = query.filter(AllocationRun.mode == mode)
        return query.order_by(AllocationRun.allocated_at.desc()).all()

    @classmethod
    def restore_allocation_run(cls, session: Session, run_id: int) -> Tuple[bool, str]:
        """Restores a historical allocation run as the active allocation in the database."""
        import json
        run = session.query(AllocationRun).filter(AllocationRun.id == run_id).first()
        if not run:
            return False, "Allocation run not found."

        is_branch_wise = run.mode == "branch_wise"
        
        # Clear existing active assignments for this mode first
        if is_branch_wise:
            session.query(Student).filter(
                Student.is_deleted == False,
                Student.status == "Active"
            ).update({
                Student.branch_venue_id: None,
                Student.branch_time_slot_id: None,
                Student.branch_venue_allocated_at: None
            }, synchronize_session=False)
        else:
            session.query(Student).filter(
                Student.is_deleted == False,
                Student.status == "Active"
            ).update({
                Student.group_venue_id: None,
                Student.group_time_slot_id: None,
                Student.group_venue_allocated_at: None,
                Student.venue_id: None,
                Student.time_slot_id: None,
                Student.venue_allocated_at: None
            }, synchronize_session=False)

        try:
            assignments = json.loads(run.assignments_json)
        except Exception as e:
            return False, f"Failed to parse run assignments: {str(e)}"

        # Pre-load venues and time slots for fast lookups
        venues = {v.name: v.id for v in session.query(Venue).all()}
        slots = {ts.slot_name: ts.id for ts in session.query(TimeSlot).all()}

        # Build dict of USN -> assignment details
        assignments_map = {a["usn"]: a for a in assignments}
        
        # Batch update students
        students = session.query(Student).filter(
            Student.is_deleted == False,
            Student.status == "Active"
        ).all()

        restored_count = 0
        for s in students:
            if s.usn in assignments_map:
                a = assignments_map[s.usn]
                v_id = venues.get(a["venue_name"])
                ts_id = slots.get(a["slot_name"])
                if is_branch_wise:
                    s.branch_venue_id = v_id
                    s.branch_time_slot_id = ts_id
                    s.branch_venue_allocated_at = run.allocated_at
                else:
                    s.group_venue_id = v_id
                    s.group_time_slot_id = ts_id
                    s.group_venue_allocated_at = run.allocated_at
                    s.venue_id = v_id
                    s.time_slot_id = ts_id
                    s.venue_allocated_at = run.allocated_at
                restored_count += 1

        audit = AuditLog(
            action="ALLOCATION_RESTORED",
            entity_type="AllocationRun",
            entity_id=str(run_id),
            details=f"Restored active venue allocations to run ID {run_id} ({run.mode}). Restored {restored_count} student assignments."
        )
        session.add(audit)
        session.commit()
        return True, f"Successfully restored {restored_count} student assignments from allocation run."


