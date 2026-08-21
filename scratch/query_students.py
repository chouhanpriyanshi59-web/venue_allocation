from database.connection import SessionLocal
from database.models import Student, Program, Department

session = SessionLocal()
try:
    students = session.query(Student).filter(Student.is_deleted == False).all()
    # Filter out student USNs starting with 1DS211_ (which is our test prefix)
    real_students = [s for s in students if not s.usn.startswith("1DS211_")]
    print(f"Total active students: {len(students)}")
    print(f"Total non-test students: {len(real_students)}")
    for s in real_students[:20]:
        print(f"Student: {s.full_name}")
        print(f"  USN: {s.usn}")
        print(f"  Program ID: {s.program_id}")
        if s.program:
            print(f"    Program Name: {s.program.name}")
        else:
            print(f"    Program: None")
        print(f"  Department ID: {s.department_id}")
        if s.department:
            print(f"    Department Code: {s.department.code}, Name: {s.department.name}")
        else:
            print(f"    Department: None")
        print("-" * 40)
finally:
    session.close()
