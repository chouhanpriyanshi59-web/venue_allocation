import pytest
from database.connection import init_db, SessionLocal
from database.models import Student, Department, Venue, TimeSlot
from engine.venue_optimizer import VenueOptimizer

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

def test_1_15_students():
    session = SessionLocal()
    
    # Setup department, venues, and timeslot
    dept = Department(name="Civil Engineering", code="CIVIL")
    session.add(dept)
    session.flush()
    
    # 15 students
    for i in range(15):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=dept.id,
            group_name="Group A" if i % 2 == 0 else "Group B",  # initially split
            status="Active"
        )
        session.add(s)
        
    v1 = Venue(name="Hall A", capacity=100, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, ts])
    session.commit()
    
    # Run Group-wise Venue Allocation
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 15
    assert len(res.warnings) == 0
    
    session.expire_all()
    
    # Verification: all in same group and same venue
    students = session.query(Student).all()
    group_names = {s.group_name for s in students}
    venue_ids = {s.group_venue_id for s in students}
    
    assert len(group_names) == 1
    assert len(venue_ids) == 1
    assert next(iter(venue_ids)) == v1.id
    
    session.close()

def test_2_20_students():
    session = SessionLocal()
    
    dept = Department(name="Civil Engineering", code="CIVIL")
    session.add(dept)
    session.flush()
    
    # 20 students
    for i in range(20):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=dept.id,
            group_name="Group A" if i % 2 == 0 else "Group B",
            status="Active"
        )
        session.add(s)
        
    v1 = Venue(name="Hall A", capacity=100, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, ts])
    session.commit()
    
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 20
    
    session.expire_all()
    students = session.query(Student).all()
    group_names = {s.group_name for s in students}
    venue_ids = {s.group_venue_id for s in students}
    
    assert len(group_names) == 1
    assert len(venue_ids) == 1
    
    session.close()

def test_3_21_students():
    session = SessionLocal()
    
    dept = Department(name="Civil Engineering", code="CIVIL")
    session.add(dept)
    session.flush()
    
    # 21 students (should NOT trigger small department rule)
    for i in range(21):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=dept.id,
            group_name="Group A" if i % 2 == 0 else "Group B",
            status="Active"
        )
        session.add(s)
        
    # We provide two venues of capacity 15 to force a split
    v1 = Venue(name="Hall A", capacity=15, is_active=True)
    v2 = Venue(name="Hall B", capacity=15, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()
    
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    # Total allocated should be 21
    assert res.newly_allocated_venues == 21
    
    session.expire_all()
    students = session.query(Student).all()
    
    # Under normal Group-wise allocation, the students are split into Group A and Group B,
    # and they can be split across venues based on group and slot capacity.
    group_names = {s.group_name for s in students}
    venue_ids = {s.group_venue_id for s in students}
    
    # Ensure they were not forced into a single group or single venue (since capacity of v1/v2 is 15, all 21 couldn't fit in one anyway)
    assert len(group_names) > 1
    assert len(venue_ids) > 1
    
    session.close()

def test_4_5_mixed_small_departments():
    session = SessionLocal()
    
    dept1 = Department(name="Civil Engineering", code="CIVIL")
    dept2 = Department(name="Mechanical Engineering", code="MECH")
    session.add_all([dept1, dept2])
    session.flush()
    
    # Civil = 15 students
    for i in range(15):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male",
            department_id=dept1.id,
            group_name="Group A",
            status="Active"
        )
        session.add(s)
        
    # Mechanical = 18 students
    for i in range(18):
        s = Student(
            usn=f"1DS21ME{i:03d}",
            full_name=f"Mech Student {i}",
            gender="Female",
            department_id=dept2.id,
            group_name="Group B",
            status="Active"
        )
        session.add(s)
        
    v1 = Venue(name="Hall A", capacity=100, is_active=True)
    v2 = Venue(name="Hall B", capacity=100, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()
    
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 33
    
    session.expire_all()
    civil_students = session.query(Student).filter(Student.department_id == dept1.id).all()
    mech_students = session.query(Student).filter(Student.department_id == dept2.id).all()
    
    assert len({s.group_name for s in civil_students}) == 1
    assert len({s.group_venue_id for s in civil_students}) == 1
    
    assert len({s.group_name for s in mech_students}) == 1
    assert len({s.group_venue_id for s in mech_students}) == 1
    
    session.close()

def test_6_insufficient_venue_capacity():
    session = SessionLocal()
    
    dept = Department(name="Civil Engineering", code="CIVIL")
    session.add(dept)
    session.flush()
    
    # 20 students
    for i in range(20):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male",
            department_id=dept.id,
            group_name="Group A",
            status="Active"
        )
        session.add(s)
        
    v1 = Venue(name="Hall A", capacity=10, is_active=True)
    v2 = Venue(name="Hall B", capacity=10, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()
    
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 0
    assert len(res.warnings) == 1
    assert "20 Civil Engineering students could not be allocated because no single available venue has sufficient capacity." in res.warnings[0]
    
    session.expire_all()
    unallocated = session.query(Student).filter(Student.group_venue_id.is_(None)).count()
    assert unallocated == 20
    
    session.close()

def test_7_sufficient_capacity():
    session = SessionLocal()
    
    dept = Department(name="Civil Engineering", code="CIVIL")
    session.add(dept)
    session.flush()
    
    # 20 students
    for i in range(20):
        s = Student(
            usn=f"1DS21CV{i:03d}",
            full_name=f"Civil Student {i}",
            gender="Male",
            department_id=dept.id,
            group_name="Group A",
            status="Active"
        )
        session.add(s)
        
    v1 = Venue(name="Hall A", capacity=200, is_active=True)
    v2 = Venue(name="Hall B", capacity=200, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()
    
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 20
    
    session.expire_all()
    students = session.query(Student).all()
    assert len({s.group_venue_id for s in students}) == 1
    
    session.close()
