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

def test_user_requested_scenarios():
    session = SessionLocal()

    # SETUP VENUES: total capacity = 1,100
    # Venue A (300), Venue B (200), Venue C (200), Venue D (200), Venue E (100), Venue F (100) -> Total = 1,100
    venues = [
        Venue(name="Venue A", capacity=300, is_active=True),
        Venue(name="Venue B", capacity=200, is_active=True),
        Venue(name="Venue C", capacity=200, is_active=True),
        Venue(name="Venue D", capacity=200, is_active=True),
        Venue(name="Venue E", capacity=100, is_active=True),
        Venue(name="Venue F", capacity=100, is_active=True),
    ]
    session.add_all(venues)
    session.commit()

    # --- Test 1: Venues total = 1,100, Slots = 1 ---
    ts1 = TimeSlot(slot_name="Slot 1", start_time="09:00 AM", end_time="10:00 AM", day_number=1)
    session.add(ts1)
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.total_capacity == 1100, f"Expected capacity 1,100 with 1 slot, got {report.total_capacity}"

    # --- Test 2: Venues total = 1,100, Slots = 3 ---
    ts2 = TimeSlot(slot_name="Slot 2", start_time="10:30 AM", end_time="11:30 AM", day_number=1)
    ts3 = TimeSlot(slot_name="Slot 3", start_time="12:00 PM", end_time="01:00 PM", day_number=1)
    session.add_all([ts2, ts3])
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.total_capacity == 1100, f"Expected capacity 1,100 with 3 slots, got {report.total_capacity}"

    # --- Test 3: Venues total = 1,100, Slots = 5 ---
    ts4 = TimeSlot(slot_name="Slot 4", start_time="01:30 PM", end_time="02:30 PM", day_number=1)
    ts5 = TimeSlot(slot_name="Slot 5", start_time="03:00 PM", end_time="04:00 PM", day_number=1)
    session.add_all([ts4, ts5])
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.total_capacity == 1100, f"Expected capacity 1,100 with 5 slots, got {report.total_capacity}"

    # --- Test 4: Increase a venue capacity by exactly 100 ---
    # We increase Venue A capacity from 300 to 400. Total capacity should increase by exactly 100 (from 1,100 to 1,200).
    venue_a = session.query(Venue).filter(Venue.name == "Venue A").first()
    venue_a.capacity = 400
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.total_capacity == 1200, f"Expected capacity 1,200 after increasing Venue A capacity, got {report.total_capacity}"

    # --- Test 5: Add another slot ---
    # Add Slot 6. Capacity should remain 1,200.
    ts6 = TimeSlot(slot_name="Slot 6", start_time="04:30 PM", end_time="05:30 PM", day_number=1)
    session.add(ts6)
    session.commit()

    report = VenueOptimizer.check_capacity(session)
    assert report.total_capacity == 1200, f"Expected capacity to remain 1,200 after adding Slot 6, got {report.total_capacity}"

    session.close()

def test_repeated_runs_produce_different_valid_allocations():
    session = SessionLocal()

    # Create active venues
    v1 = Venue(name="Venue X", capacity=30, is_active=True)
    v2 = Venue(name="Venue Y", capacity=30, is_active=True)
    ts = TimeSlot(slot_name="Slot Alpha", start_time="09:00 AM", end_time="11:00 AM", day_number=1)
    session.add_all([v1, v2, ts])

    # Create department
    dept = Department(name="Information Science", code="ISE")
    session.add(dept)
    session.commit()

    # Create 50 students
    for i in range(50):
        s = Student(
            usn=f"1DS21IS{i:03d}",
            full_name=f"ISE Student {i}",
            gender="Male" if i % 2 == 0 else "Female",
            department_id=dept.id,
            group_name="Group A",
            status="Active"
        )
        session.add(s)
    session.commit()

    # First Allocation Run
    res1 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res1.newly_allocated_venues == 50

    session.expire_all()
    first_assignments = {s.usn: s.group_venue_id for s in session.query(Student).all()}

    # Second Allocation Run
    res2 = VenueOptimizer.optimize_allocations(mode="group_wise", auto_backup=False)
    assert res2.newly_allocated_venues == 50

    session.expire_all()
    second_assignments = {s.usn: s.group_venue_id for s in session.query(Student).all()}

    # Check that at least some student assignments have changed due to randomization (shuffle)
    assignment_changes = sum(1 for usn, v_id in first_assignments.items() if second_assignments[usn] != v_id)
    assert assignment_changes > 0, "Expected randomization to produce a different allocation pattern on second run"

    session.close()

