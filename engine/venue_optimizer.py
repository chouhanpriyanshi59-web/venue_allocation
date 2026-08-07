import math
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Student, Department, Venue, TimeSlot, AuditLog
from database.backup_manager import BackupManager
from core.domain_models import AllocationResult, CapacityReport
from core.exceptions import CapacityExceededError

class VenueOptimizer:
    """
    Proportional Stratified Multi-Criteria Optimization & Occupancy Balancing Engine.
    
    Ensures:
    1. Proportional representation of every Department across all venues.
    2. Proportional Gender ratios matching overall population per venue.
    3. Balanced occupancy rates across available venues (no under-utilized venues).
    4. Strict adherence to max venue capacities.
    5. Deterministic placement based on student USN / ID.
    6. Efficient scalability to 10,000+ students.
    """

    @classmethod
    def check_capacity(cls, session: Session, target_group: Optional[str] = None) -> CapacityReport:
        """Evaluates whether current active venues and time slots have sufficient capacity."""
        query = session.query(Student).filter(
            Student.is_deleted == False,
            Student.status == "Active",
            Student.venue_id.is_(None)
        )
        if target_group:
            query = query.filter(Student.group_name == target_group)

        total_students = query.count()

        active_venues = session.query(Venue).filter(Venue.is_active == True).all()
        time_slots = session.query(TimeSlot).all()

        total_capacity_per_slot = sum(v.capacity for v in active_venues)
        total_capacity = total_capacity_per_slot * len(time_slots)

        is_sufficient = total_capacity >= total_students
        deficiency = max(0, total_students - total_capacity)

        suggested_per_slot = {}
        if deficiency > 0 and len(time_slots) > 0:
            extra_per_slot = (deficiency + len(time_slots) - 1) // len(time_slots)
            for ts in time_slots:
                suggested_per_slot[ts.slot_name] = extra_per_slot

        return CapacityReport(
            total_students=total_students,
            total_capacity=total_capacity,
            is_sufficient=is_sufficient,
            deficiency=deficiency,
            suggested_per_slot=suggested_per_slot
        )

    @classmethod
    def _distribute_venue_capacities(
        cls,
        venues: List[Venue],
        slot_student_count: int
    ) -> Dict[int, int]:
        """
        Calculates balanced target student capacities per venue for a given slot
        using Hamilton-Hare (Largest Remainder) proportional distribution.
        """
        total_slot_capacity = sum(v.capacity for v in venues)
        if total_slot_capacity == 0 or slot_student_count == 0:
            return {v.id: 0 for v in venues}

        ratio = min(1.0, slot_student_count / total_slot_capacity)
        
        base_alloc: Dict[int, int] = {}
        remainders: List[Tuple[float, int, int]] = [] # (remainder, max_cap, venue_id)

        for v in venues:
            exact = v.capacity * ratio
            base = min(int(exact), v.capacity)
            base_alloc[v.id] = base
            rem = exact - base
            remainders.append((rem, v.capacity, v.id))

        assigned = sum(base_alloc.values())
        deficit = slot_student_count - assigned

        # Sort by remainder descending, then capacity descending
        remainders.sort(key=lambda x: (x[0], x[1]), reverse=True)

        idx = 0
        while deficit > 0 and remainders:
            rem, max_cap, v_id = remainders[idx % len(remainders)]
            if base_alloc[v_id] < max_cap:
                base_alloc[v_id] += 1
                deficit -= 1
            idx += 1
            if idx > len(remainders) * 100: # Safety break
                break

        return base_alloc

    @classmethod
    def _allocate_strata_matrix(
        cls,
        venue_targets: Dict[int, int],
        strata_students: Dict[Tuple[int, str], List[Student]]
    ) -> Dict[Tuple[int, Tuple[int, str]], int]:
        """
        Uses 2D Largest Remainder matrix rounding to allocate stratum counts (department, gender)
        to venues, maintaining exact row sums (venue targets) and col sums (stratum counts).
        
        Returns dict mapping (venue_id, (department_id, gender)) -> int count.
        """
        v_ids = list(venue_targets.keys())
        strata_keys = list(strata_students.keys())
        total_students = sum(len(s_list) for s_list in strata_students.values())

        if total_students == 0 or not v_ids:
            return {}

        # 1. Continuous ideal matrix Q[v, k]
        # Q[v, k] = T_v * (N_k / Total)
        exact_matrix: Dict[Tuple[int, Tuple[int, str]], float] = {}
        base_matrix: Dict[Tuple[int, Tuple[int, str]], int] = {}
        remainders: List[Tuple[float, int, Tuple[int, str]]] = []

        for v_id in v_ids:
            t_v = venue_targets[v_id]
            for s_key in strata_keys:
                n_k = len(strata_students[s_key])
                exact = (t_v * n_k) / total_students
                base = int(exact)
                exact_matrix[(v_id, s_key)] = exact
                base_matrix[(v_id, s_key)] = base
                remainders.append((exact - base, v_id, s_key))

        # Check deficits
        row_deficits = {v_id: venue_targets[v_id] - sum(base_matrix[(v_id, k)] for k in strata_keys) for v_id in v_ids}
        col_deficits = {k: len(strata_students[k]) - sum(base_matrix[(v, k)] for v in v_ids) for k in strata_keys}

        # Sort remainders descending
        remainders.sort(key=lambda item: item[0], reverse=True)

        for rem, v_id, s_key in remainders:
            if row_deficits[v_id] > 0 and col_deficits[s_key] > 0:
                base_matrix[(v_id, s_key)] += 1
                row_deficits[v_id] -= 1
                col_deficits[s_key] -= 1

        # Residual sweep if any remain due to zero remainders
        for v_id in v_ids:
            while row_deficits[v_id] > 0:
                allocated = False
                for s_key in strata_keys:
                    if col_deficits[s_key] > 0:
                        base_matrix[(v_id, s_key)] += 1
                        row_deficits[v_id] -= 1
                        col_deficits[s_key] -= 1
                        allocated = True
                        break
                if not allocated:
                    break

        return base_matrix

    @classmethod
    def _partition_venues_by_group(
        cls,
        venues: List[Venue],
        group_counts: Dict[str, int]
    ) -> Dict[str, List[Venue]]:
        """
        Partitions available active venues among active student groups for a single time slot,
        guaranteeing that every venue is assigned to at most ONE group in this slot.
        """
        if not group_counts or not venues:
            return {}

        active_groups = [g for g, cnt in group_counts.items() if cnt > 0]
        if not active_groups:
            return {}

        # If only 1 group needs allocation, all venues go to that group
        if len(active_groups) == 1:
            return {active_groups[0]: list(venues)}

        # Sort groups deterministically (by student count descending, then group name ascending)
        sorted_groups = sorted(active_groups, key=lambda g: (-group_counts[g], g))

        total_students = sum(group_counts[g] for g in sorted_groups)
        total_venue_capacity = sum(v.capacity for v in venues)

        # Target capacity per group proportional to its demand
        group_target_caps = {}
        for g in sorted_groups:
            exact = (total_venue_capacity * group_counts[g]) / max(1, total_students)
            group_target_caps[g] = int(round(exact))

        # Sort venues by capacity descending, then ID ascending for deterministic assignment
        sorted_venues = sorted(venues, key=lambda v: (-v.capacity, v.id))

        assigned: Dict[str, List[Venue]] = {g: [] for g in sorted_groups}
        assigned_caps: Dict[str, int] = {g: 0 for g in sorted_groups}

        # Assign discrete venues to groups greedily by capacity deficiency
        for v in sorted_venues:
            best_group = None
            max_deficiency = -float('inf')

            for g in sorted_groups:
                needed = min(group_counts[g], group_target_caps[g])
                deficiency = needed - assigned_caps[g]
                if deficiency > max_deficiency:
                    max_deficiency = deficiency
                    best_group = g

            if best_group is None:
                best_group = sorted_groups[0]

            assigned[best_group].append(v)
            assigned_caps[best_group] += v.capacity

        return assigned

    @classmethod
    def optimize_allocations(
        cls,
        target_group: Optional[str] = None,
        allow_department_splits: bool = True,
        auto_backup: bool = True
    ) -> AllocationResult:
        """
        Executes Group-Isolated Proportional Stratified Occupancy Balancing optimization.
        Guarantees that every venue in any time slot contains students from ONLY ONE group.
        """
        if auto_backup:
            BackupManager.create_backup(trigger_action="PRE_VENUE_ALLOCATION")

        session: Session = SessionLocal()
        try:
            # 1. Check Capacity
            cap_report = cls.check_capacity(session, target_group)
            if not cap_report.is_sufficient:
                raise CapacityExceededError(
                    f"Insufficient total venue capacity! Total students needing allocation: {cap_report.total_students}, Total available capacity: {cap_report.total_capacity}. Shortfall: {cap_report.deficiency} seats.",
                    required_capacity=cap_report.total_students,
                    available_capacity=cap_report.total_capacity
                )

            # 2. Query target unallocated active students
            query = session.query(Student).filter(
                Student.is_deleted == False,
                Student.status == "Active",
                Student.venue_id.is_(None)
            )
            if target_group:
                query = query.filter(Student.group_name == target_group)

            unallocated_students = query.all()
            if not unallocated_students:
                return AllocationResult(
                    total_processed=0,
                    newly_allocated_groups=0,
                    newly_allocated_venues=0,
                    skipped_existing=0,
                    warnings=["No unallocated students found for venue assignment."]
                )

            venues = session.query(Venue).filter(Venue.is_active == True).all()
            time_slots = session.query(TimeSlot).all()

            if not venues:
                raise ValueError("No active venues found. Please configure venues first.")
            if not time_slots:
                raise ValueError("No time slots found. Please configure time slots first.")

            # Sort venues and time slots deterministically by ID
            venues.sort(key=lambda v: v.id)
            time_slots.sort(key=lambda t: t.id)

            # Organize unallocated students by group
            groups_unallocated: Dict[str, List[Student]] = {}
            for s in unallocated_students:
                g_key = s.group_name or "Unassigned"
                if g_key not in groups_unallocated:
                    groups_unallocated[g_key] = []
                groups_unallocated[g_key].append(s)

            # Sort students within each group deterministically by USN / ID
            for g_key in groups_unallocated:
                groups_unallocated[g_key].sort(key=lambda s: (s.usn or "", s.full_name or "", s.id))

            total_unallocated = len(unallocated_students)
            allocated_count = 0
            now = datetime.utcnow()

            # Process Slot by Slot with Group-Dedicated Venues
            for t_slot in time_slots:
                # Filter active groups with remaining students
                active_group_counts = {g: len(stus) for g, stus in groups_unallocated.items() if len(stus) > 0}
                if not active_group_counts:
                    break

                # Partition venues among active groups for this slot
                partitioned_venues = cls._partition_venues_by_group(venues, active_group_counts)

                # Process each group independently within its dedicated venues
                for g_name, g_venues in partitioned_venues.items():
                    if not g_venues:
                        continue

                    g_students = groups_unallocated.get(g_name, [])
                    if not g_students:
                        continue

                    g_slot_capacity = sum(v.capacity for v in g_venues)
                    count_to_take = min(len(g_students), g_slot_capacity)

                    # Slice students for this slot
                    slot_g_students = g_students[:count_to_take]
                    groups_unallocated[g_name] = g_students[count_to_take:]

                    # Step A: Proportional Balanced Venue Capacities for this Group's Venues
                    venue_targets = cls._distribute_venue_capacities(g_venues, count_to_take)

                    # Step B: Stratify group students by (department_id, gender)
                    strata_students: Dict[Tuple[int, str], List[Student]] = {}
                    for s in slot_g_students:
                        s_key = (s.department_id or 0, s.gender or "Unknown")
                        if s_key not in strata_students:
                            strata_students[s_key] = []
                        strata_students[s_key].append(s)

                    # Step C: Generate Proportional Stratum Matrix
                    matrix_alloc = cls._allocate_strata_matrix(venue_targets, strata_students)

                    # Step D: Deterministically assign students to dedicated venues
                    strata_indices: Dict[Tuple[int, str], int] = {k: 0 for k in strata_students}

                    for v in g_venues:
                        v_id = v.id
                        for s_key, s_list in strata_students.items():
                            assign_count = matrix_alloc.get((v_id, s_key), 0)
                            if assign_count > 0:
                                curr_start = strata_indices[s_key]
                                sub_group = s_list[curr_start : curr_start + assign_count]
                                strata_indices[s_key] += assign_count

                                for s in sub_group:
                                    s.venue_id = v_id
                                    s.time_slot_id = t_slot.id
                                    s.venue_allocated_at = now
                                    allocated_count += 1

            # Verification Assertion: Ensure no venue in any time slot contains multiple groups
            allocated_pairs = session.query(
                Student.time_slot_id, Student.venue_id, Student.group_name
            ).filter(
                Student.is_deleted == False,
                Student.venue_id.isnot(None),
                Student.time_slot_id.isnot(None)
            ).distinct().all()

            slot_venue_map: Dict[Tuple[int, int], set] = {}
            for ts_id, v_id, g_name in allocated_pairs:
                key = (ts_id, v_id)
                if key not in slot_venue_map:
                    slot_venue_map[key] = set()
                slot_venue_map[key].add(g_name or "Unassigned")

            for (ts_id, v_id), g_set in slot_venue_map.items():
                if len(g_set) > 1:
                    session.rollback()
                    raise RuntimeError(
                        f"Group isolation violation detected! Venue ID {v_id} in Time Slot ID {ts_id} contains multiple groups: {g_set}"
                    )

            # Log audit
            audit = AuditLog(
                action="VENUE_OPTIMIZATION_SUCCESS",
                entity_type="VenueAllocation",
                details=f"Proportionally allocated {allocated_count} students to group-isolated venues across {len(time_slots)} slots."
            )
            session.add(audit)
            session.commit()

            return AllocationResult(
                total_processed=total_unallocated,
                newly_allocated_groups=0,
                newly_allocated_venues=allocated_count,
                skipped_existing=0
            )

        except CapacityExceededError:
            session.rollback()
            raise
        except Exception as e:
            session.rollback()
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Venue optimization failed: {str(e)}")
        finally:
            session.close()

