from database.connection import SessionLocal
from database.models import Program, Department, Student

session = SessionLocal()
try:
    print("--- DEPARTMENTS ---")
    depts = session.query(Department).all()
    for d in depts:
        print(f"ID: {d.id}, Code: {d.code}, Name: {d.name}")

    print("\n--- PROGRAMS ---")
    progs = session.query(Program).all()
    for p in progs:
        print(f"ID: {p.id}, Code: {p.code}, Name: {p.name}")

    print("\n--- NON-TEST STUDENTS (FIRST 10) ---")
    stus = session.query(Student).filter(Student.is_deleted == False).all()
    real_stus = [s for s in stus if not s.usn.startswith("1DS211_") and not s.usn.startswith("1DS212_") and not s.usn.startswith("1DS213_") and not s.usn.startswith("1DS214_")]
    print(f"Total non-test students: {len(real_stus)}")
    for s in real_stus[:10]:
        print(f"Student: {s.full_name}, USN: {s.usn}, Program ID: {s.program_id}, Dept ID: {s.department_id}")
        if s.program:
            print(f"  Program: {s.program.name}")
        if s.department:
            print(f"  Department: {s.department.name} ({s.department.code})")
finally:
    session.close()
