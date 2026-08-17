import time
import pytest
from pathlib import Path
from database.connection import init_db, SessionLocal
from database.models import Student, Department, Venue, TimeSlot
from engine.group_allocator import GroupAllocator
from engine.venue_optimizer import VenueOptimizer
from services.export_service import ExportService
from config import EXPORTS_DIR

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    session = SessionLocal()
    session.query(Student).delete()
    session.query(Department).delete()
    session.query(Venue).delete()
    session.query(TimeSlot).delete()
    session.commit()
    session.close()

def test_10k_student_benchmark():
    session = SessionLocal()

    # Create 5 Departments
    depts = [
        Department(name="Computer Science & Engineering", code="CSE"),
        Department(name="Information Science", code="ISE"),
        Department(name="Electronics & Comm", code="ECE"),
        Department(name="Mechanical Engineering", code="MECH"),
        Department(name="Civil Engineering", code="CIVIL"),
    ]
    session.add_all(depts)
    session.commit()

    # Create 10 Venues & 5 Time Slots -> Capacity 10 * 1000 = 10,000 seats
    venues = [Venue(name=f"Main Hall {i+1}", capacity=1000, is_active=True) for i in range(10)]
    session.add_all(venues)
    
    time_slots = [TimeSlot(slot_name=f"Slot {i+1}", start_time=f"0{i+8}:00 AM", end_time=f"10:00 AM", day_number=1) for i in range(5)]
    session.add_all(time_slots)
    session.commit()

    # Seed 10,000 synthetic students
    print("\n[BENCHMARK] Generating 10,000 synthetic student records...")
    t0 = time.time()
    
    students = []
    for i in range(10000):
        d_idx = i % len(depts)
        s = Student(
            usn=f"1DS23CS{i:05d}",
            full_name=f"Student Candidate {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=depts[d_idx].id,
            status="Active"
        )
        students.append(s)

    session.bulk_save_objects(students)
    session.commit()
    t_gen = time.time() - t0
    print(f"[BENCHMARK] 10,000 records seeded into SQLite in {t_gen:.2f}s")

    # Benchmark Group Allocation
    t0 = time.time()
    res_grp = GroupAllocator.allocate_groups(auto_backup=False)
    t_grp = time.time() - t0
    print(f"[BENCHMARK] Group Allocation for 10,000 students completed in {t_grp:.2f}s")
    assert res_grp.newly_allocated_groups == 10000

    # Benchmark Venue Allocation
    t0 = time.time()
    res_ven = VenueOptimizer.optimize_allocations(auto_backup=False)
    t_ven = time.time() - t0
    print(f"[BENCHMARK] Proportional Stratified Venue Allocation for 10,000 students completed in {t_ven:.2f}s")
    assert res_ven.newly_allocated_venues == 10000

    # Benchmark Export
    t0 = time.time()
    exp_path = EXPORTS_DIR / "Benchmark_10k_Master.xlsx"
    ExportService.export_excel_master(exp_path)
    t_exp = time.time() - t0
    print(f"[BENCHMARK] Multi-sheet Excel Export for 10,000 students completed in {t_exp:.2f}s")
    assert exp_path.exists()

    session.close()
