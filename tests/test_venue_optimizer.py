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

def test_venue_capacity_check_and_optimization():
    session = SessionLocal()

    v1 = Venue(name="Auditorium 1", capacity=10, is_active=True)
    v2 = Venue(name="Seminar Hall B", capacity=10, is_active=True)
    ts1 = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts1])
    
    dept = Department(name="Computer Science", code="CSE")
    session.add(dept)
    session.commit()

    # Add 25 students (Total capacity = 20) -> Should fail capacity check!
    for i in range(25):
        s = Student(usn=f"1DS21CS{i:03d}", full_name=f"Stu {i}", department_id=dept.id, group_name="Group A")
        session.add(s)
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.is_sufficient is False
    assert report.deficiency == 5

    res_fail = VenueOptimizer.optimize_allocations(auto_backup=False)
    assert any("insufficient venue capacity" in w for w in res_fail.warnings)

    # Increase capacity to 30 by adding another Time Slot
    ts2 = TimeSlot(slot_name="Slot 2", start_time="11:30 AM", end_time="01:30 PM", day_number=1)
    session.add(ts2)
    session.commit()

    # Now total capacity = 2 venues * 2 slots * 10 cap = 40 >= 25 -> Should succeed!
    res = VenueOptimizer.optimize_allocations(auto_backup=False)
    assert res.newly_allocated_venues == 5
    assert session.query(Student).filter(Student.group_venue_id.isnot(None)).count() == 25
    session.close()

def test_venue_and_timeslot_deletion():
    from database.repository import Repository
    session = SessionLocal()

    v1 = Venue(name="Venue To Delete", capacity=50, is_active=True)
    ts1 = TimeSlot(slot_name="Slot To Delete", start_time="02:00 PM", end_time="04:00 PM", day_number=1)
    session.add_all([v1, ts1])
    session.commit()

    student = Student(usn="1DS21CS999", full_name="Test Student", venue_id=v1.id, time_slot_id=ts1.id)
    session.add(student)
    session.commit()

    # Delete venue
    ok, msg = Repository.delete_venue(session, v1.id)
    assert ok is True
    assert session.query(Venue).filter(Venue.name == "Venue To Delete").first() is None
    
    session.refresh(student)
    assert student.venue_id is None

    # Delete timeslot
    ok_ts, msg_ts = Repository.delete_time_slot(session, ts1.id)
    assert ok_ts is True
    assert session.query(TimeSlot).filter(TimeSlot.slot_name == "Slot To Delete").first() is None
    
    session.close()

def test_proportional_and_balanced_venue_allocation():
    session = SessionLocal()

    # 1. Setup 5 Departments
    dept_specs = [
        ("CSE", 50, 50),
        ("ISE", 50, 50),
        ("ECE", 50, 50),
        ("AIML", 70, 30),
        ("MECH", 70, 30),
    ]

    depts = {}
    for code, m_cnt, f_cnt in dept_specs:
        d = Department(name=f"Department {code}", code=code)
        session.add(d)
        session.flush()
        depts[code] = d

    # 2. Add 500 Students
    for code, m_cnt, f_cnt in dept_specs:
        d_id = depts[code].id
        for i in range(m_cnt):
            s = Student(usn=f"1DS21{code}M{i:03d}", full_name=f"{code} Male {i}", gender="Male", department_id=d_id, status="Active")
            session.add(s)
        for i in range(f_cnt):
            s = Student(usn=f"1DS21{code}F{i:03d}", full_name=f"{code} Female {i}", gender="Female", department_id=d_id, status="Active")
            session.add(s)

    # 3. Add 2 Venues (ECE Seminar Hall: 500, Civil Hall: 200) & 1 Slot
    v1 = Venue(name="ECE Seminar Hall", capacity=500, is_active=True)
    v2 = Venue(name="Civil Hall", capacity=200, is_active=True)
    ts = TimeSlot(slot_name="Morning Session", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()

    # 4. Run Optimization
    res = VenueOptimizer.optimize_allocations(auto_backup=False)
    assert res.newly_allocated_venues == 500

    # 5. Verify Proportionality and Occupancy Balancing
    v1_students = session.query(Student).filter(Student.venue_id == v1.id).all()
    v2_students = session.query(Student).filter(Student.venue_id == v2.id).all()

    # Check Total Counts (Balanced ~357 in V1, ~143 in V2)
    assert len(v1_students) == 357
    assert len(v2_students) == 143

    # Check Department representation (Every dept in both venues)
    for code, _, _ in dept_specs:
        d_id = depts[code].id
        v1_dept_cnt = len([s for s in v1_students if s.department_id == d_id])
        v2_dept_cnt = len([s for s in v2_students if s.department_id == d_id])

        # CSE, ISE, ECE, AIML, MECH each get 71 or 72 in V1, 28 or 29 in V2
        assert 70 <= v1_dept_cnt <= 73
        assert 27 <= v2_dept_cnt <= 30
        assert v1_dept_cnt + v2_dept_cnt == 100

    # Check Gender Proportions (290 Male, 210 Female total -> ~207M / ~150F in V1, ~83M / ~60F in V2)
    v1_males = len([s for s in v1_students if s.gender == "Male"])
    v1_females = len([s for s in v1_students if s.gender == "Female"])
    v2_males = len([s for s in v2_students if s.gender == "Male"])
    v2_females = len([s for s in v2_students if s.gender == "Female"])

    assert 200 <= v1_males <= 215
    assert 140 <= v1_females <= 155
    assert 75 <= v2_males <= 90
    assert 55 <= v2_females <= 65

    session.close()

def test_group_isolation_in_venues():
    session = SessionLocal()

    # Create 2 Departments
    d1 = Department(name="CSE", code="CSE")
    d2 = Department(name="ECE", code="ECE")
    session.add_all([d1, d2])
    session.flush()

    # Create 500 Students: 250 in Group A, 250 in Group B
    for i in range(250):
        s1 = Student(usn=f"1DS21GA{i:03d}", full_name=f"Group A Stu {i}", gender="Male" if i % 2 == 0 else "Female", department_id=d1.id if i % 2 == 0 else d2.id, group_name="Group A", status="Active")
        s2 = Student(usn=f"1DS21GB{i:03d}", full_name=f"Group B Stu {i}", gender="Male" if i % 2 == 0 else "Female", department_id=d1.id if i % 2 == 0 else d2.id, group_name="Group B", status="Active")
        session.add_all([s1, s2])

    # Create 2 Venues (ECE Hall: 500 cap, Civil Hall: 200 cap) and 2 Time Slots
    v1 = Venue(name="ECE Seminar Hall", capacity=500, is_active=True)
    v2 = Venue(name="Civil Hall", capacity=200, is_active=True)
    ts1 = TimeSlot(slot_name="Morning Session", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    ts2 = TimeSlot(slot_name="Afternoon Session", start_time="02:00 PM", end_time="04:00 PM", day_number=1)
    session.add_all([v1, v2, ts1, ts2])
    session.commit()

    # Run Venue Optimization
    res = VenueOptimizer.optimize_allocations(auto_backup=False)
    assert res.newly_allocated_venues == 500

    # Verify Group Isolation: NO venue in ANY slot should contain both Group A and Group B
    allocated_pairs = session.query(
        Student.time_slot_id, Student.venue_id, Student.group_name
    ).filter(
        Student.is_deleted == False,
        Student.venue_id.isnot(None)
    ).distinct().all()

    slot_venue_map = {}
    for ts_id, v_id, g_name in allocated_pairs:
        key = (ts_id, v_id)
        if key not in slot_venue_map:
            slot_venue_map[key] = set()
        slot_venue_map[key].add(g_name)

    session.close()

def test_branch_wise_venue_allocation_even_split():
    session = SessionLocal()

    # Create Department MECH
    mech = Department(name="Mechanical Engineering", code="MECH")
    cse = Department(name="Computer Science", code="CSE")
    session.add_all([mech, cse])
    session.flush()

    # Add 450 MECH students
    for i in range(450):
        s = Student(usn=f"1DS21ME{i:03d}", full_name=f"MECH Stu {i}", gender="Male" if i % 2 == 0 else "Female", department_id=mech.id, status="Active")
        session.add(s)

    # Create 3 Halls (200 capacity each) & 1 Time Slot
    h1 = Venue(name="Hall A", capacity=200, is_active=True)
    h2 = Venue(name="Hall B", capacity=200, is_active=True)
    h3 = Venue(name="Hall C", capacity=200, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([h1, h2, h3, ts])
    session.commit()

    # Run Branch-wise Allocation
    res = VenueOptimizer.optimize_allocations(mode="branch_wise", auto_backup=False)
    assert res.newly_allocated_venues == 450

    # Verify Even Split: 450 MECH students across 3 halls of cap 200 should be [150, 150, 150]
    h1_stus = session.query(Student).filter(Student.branch_venue_id == h1.id).count()
    h2_stus = session.query(Student).filter(Student.branch_venue_id == h2.id).count()
    h3_stus = session.query(Student).filter(Student.branch_venue_id == h3.id).count()

    assert h1_stus == 150
    assert h2_stus == 150
    assert h3_stus == 150

    session.close()

def test_branch_wise_500_students_split():
    session = SessionLocal()

    mech = Department(name="Mechanical Engineering", code="MECH")
    session.add(mech)
    session.flush()

    # Add 500 MECH students
    for i in range(500):
        s = Student(usn=f"1DS21ME{i:03d}", full_name=f"MECH Stu {i}", gender="Male" if i % 2 == 0 else "Female", department_id=mech.id, status="Active")
        session.add(s)

    h1 = Venue(name="Hall A", capacity=200, is_active=True)
    h2 = Venue(name="Hall B", capacity=200, is_active=True)
    h3 = Venue(name="Hall C", capacity=200, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([h1, h2, h3, ts])
    session.commit()

    # Run Branch-wise Allocation
    res = VenueOptimizer.optimize_allocations(mode="branch_wise", auto_backup=False)
    assert res.newly_allocated_venues == 500

    # Verify Even Split: 500 MECH students across 3 halls of cap 200 should be approx [167, 167, 166]
    counts = sorted([
        session.query(Student).filter(Student.branch_venue_id == h1.id).count(),
        session.query(Student).filter(Student.branch_venue_id == h2.id).count(),
        session.query(Student).filter(Student.branch_venue_id == h3.id).count()
    ], reverse=True)

    assert counts == [167, 167, 166]

    session.close()

def test_coexisting_group_and_branch_wise_allocations():
    session = SessionLocal()

    mech = Department(name="Mechanical Engineering", code="MECH")
    cse = Department(name="Computer Science", code="CSE")
    session.add_all([mech, cse])
    session.flush()

    # Add 100 students in Group A & B
    for i in range(100):
        s = Student(
            usn=f"1DS21CO{i:03d}",
            full_name=f"Coexist Stu {i}",
            department_id=mech.id if i % 2 == 0 else cse.id,
            group_name="Group A" if i < 50 else "Group B",
            status="Active"
        )
        session.add(s)

    v1 = Venue(name="Hall 1", capacity=60, is_active=True)
    v2 = Venue(name="Hall 2", capacity=60, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()

    # Step 1: Run Group-wise Allocation
    res1 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res1.newly_allocated_venues == 100

    stus_after_group = session.query(Student).all()
    for s in stus_after_group:
        assert s.group_venue_id is not None
        assert s.group_time_slot_id is not None
        assert s.branch_venue_id is None

    # Step 2: Run Branch-wise Allocation
    res2 = VenueOptimizer.optimize_allocations(mode="branch_wise", auto_backup=False)
    assert res2.newly_allocated_venues == 100

    session.expire_all()
    stus_after_both = session.query(Student).all()
    for s in stus_after_both:
        # Both allocations exist simultaneously!
        assert s.group_venue_id is not None
        assert s.group_time_slot_id is not None
        assert s.branch_venue_id is not None
        assert s.branch_time_slot_id is not None

    session.close()

def test_user_700_student_5_branch_single_venue_priority():
    session = SessionLocal()

    depts = [
        Department(name="Computer Science", code="CSE"),
        Department(name="Electronics", code="ECE"),
        Department(name="Mechanical", code="MECH"),
        Department(name="Civil", code="CIVIL"),
        Department(name="Electrical", code="EEE")
    ]
    session.add_all(depts)
    session.flush()

    # Create 140 students for each of the 5 departments (700 total)
    for d in depts:
        for i in range(140):
            s = Student(
                usn=f"1DS21{d.code}{i:03d}",
                full_name=f"{d.code} Student {i}",
                gender="Male" if i % 2 == 0 else "Female",
                department_id=d.id,
                status="Active"
            )
            session.add(s)

    v_a = Venue(name="Venue A", capacity=200, is_active=True)
    v_b = Venue(name="Venue B", capacity=200, is_active=True)
    v_c = Venue(name="Venue C", capacity=200, is_active=True)
    v_d = Venue(name="Venue D", capacity=100, is_active=True)
    v_e = Venue(name="Venue E", capacity=200, is_active=True)
    v_f = Venue(name="Venue F", capacity=200, is_active=True)

    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v_a, v_b, v_c, v_d, v_e, v_f, ts])
    session.commit()

    # Run Branch-wise Allocation
    res = VenueOptimizer.optimize_allocations(mode="branch_wise", auto_backup=False)
    assert res.newly_allocated_venues == 700

    session.expire_all()

    # Verify that every department is in EXACTLY 1 venue
    for d in depts:
        assigned_venues = session.query(Student.branch_venue_id).filter(
            Student.department_id == d.id
        ).distinct().all()
        assert len(assigned_venues) == 1, f"Department {d.code} was split across multiple venues!"

    # Verify Venue D (capacity 100) is left empty (0 students)
    v_d_count = session.query(Student).filter(Student.branch_venue_id == v_d.id).count()
    assert v_d_count == 0, f"Venue D should be empty, but contains {v_d_count} students!"

    session.close()

def test_insufficient_capacity_handling():
    session = SessionLocal()

    dept = Department(name="Mechanical Engineering", code="MECH")
    session.add(dept)
    session.flush()

    # Create 150 students in Group B
    for i in range(150):
        s = Student(
            usn=f"1DS21ME{i:03d}",
            full_name=f"Mech Stu {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=dept.id,
            group_name="Group B",
            status="Active"
        )
        session.add(s)

    # Total capacity = 100 (1 venue, 1 slot)
    v_c = Venue(name="Hall C", capacity=100, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v_c, ts])
    session.commit()

    # Run Group-wise Allocation
    res = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res.newly_allocated_venues == 100
    assert len(res.warnings) == 1
    assert "Group B has insufficient venue capacity" in res.warnings[0]
    assert "Required Capacity: 150" in res.warnings[0]
    assert "Available Capacity: 100" in res.warnings[0]
    assert "Unallocated Students: 50" in res.warnings[0]

    session.expire_all()

    # 100 should be allocated, 50 unallocated
    allocated = session.query(Student).filter(Student.group_venue_id.isnot(None)).all()
    unallocated = session.query(Student).filter(Student.group_venue_id.is_(None)).all()
    assert len(allocated) == 100
    assert len(unallocated) == 50

    # Store IDs of allocated students to verify recovery leaves them unchanged
    allocated_ids = {s.id for s in allocated}

    # Recovery: Add new venue of 100 capacity
    v_new = Venue(name="Hall New", capacity=100, is_active=True)
    session.add(v_new)
    session.commit()

    # Run Group-wise Allocation again
    res2 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res2.newly_allocated_venues == 50
    assert len(res2.warnings) == 0

    session.expire_all()

    # All 150 should now be allocated
    all_allocated = session.query(Student).filter(Student.group_venue_id.isnot(None)).all()
    assert len(all_allocated) == 150

    # Verify that original 100 students' allocations are unchanged
    for s in all_allocated:
        if s.id in allocated_ids:
            assert s.group_venue_id == v_c.id
        else:
            assert s.group_venue_id == v_new.id

    session.close()

def test_group_isolation_incremental_locking():
    session = SessionLocal()

    d1 = Department(name="CSE", code="CSE")
    d2 = Department(name="ECE", code="ECE")
    session.add_all([d1, d2])
    session.flush()

    # Create 250 Group A students and 250 Group B students
    for i in range(250):
        s1 = Student(
            usn=f"1DS21GA{i:03d}",
            full_name=f"GA Stu {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=d1.id if i % 2 == 0 else d2.id,
            group_name="Group A",
            status="Active"
        )
        s2 = Student(
            usn=f"1DS21GB{i:03d}",
            full_name=f"GB Stu {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=d1.id if i % 2 == 0 else d2.id,
            group_name="Group B",
            status="Active"
        )
        session.add_all([s1, s2])

    # 2 Venues: ECE Hall (500), Civil Hall (200)
    v1 = Venue(name="ECE Seminar Hall", capacity=500, is_active=True)
    v2 = Venue(name="Civil Hall", capacity=200, is_active=True)
    ts = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])
    session.commit()

    # First run:
    # ECE Hall (500) will allocate all 250 Group A students.
    # Civil Hall (200) will allocate 200 Group B students.
    # 50 Group B students will remain unallocated.
    res1 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res1.newly_allocated_venues == 450
    assert len(res1.warnings) == 1
    assert "Group B has insufficient venue capacity" in res1.warnings[0]

    session.expire_all()

    # Verify database state after run 1
    v1_group = session.query(Student.group_name).filter(Student.group_venue_id == v1.id).distinct().all()
    v2_group = session.query(Student.group_name).filter(Student.group_venue_id == v2.id).distinct().all()
    assert [g[0] for g in v1_group] == ["Group A"]
    assert [g[0] for g in v2_group] == ["Group B"]

    # Second run (without adding capacity):
    # The remaining 50 Group B students cannot go to ECE Hall because it is locked to Group A.
    # Since Civil Hall is full, they should not be allocated.
    res2 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res2.newly_allocated_venues == 0
    assert len(res2.warnings) == 1
    assert "Group B has insufficient venue capacity" in res2.warnings[0]

    session.expire_all()

    # Verify no group isolation violations
    v1_group_after = session.query(Student.group_name).filter(Student.group_venue_id == v1.id).distinct().all()
    assert [g[0] for g in v1_group_after] == ["Group A"]

    session.close()







