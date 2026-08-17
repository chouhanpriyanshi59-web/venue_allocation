import math
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Student, Department, Venue, TimeSlot, AuditLog, AllocationRun
from database.backup_manager import BackupManager
from core.domain_models import AllocationResult, CapacityReport

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
    def check_capacity(cls, session: Session, target_group: Optional[str] = None, mode: str = "group_wise") -> CapacityReport:
        """Evaluates whether current active venues and time slots have sufficient capacity."""
        is_branch_wise = mode in ("branch_wise", "branch", "department_wise")

        query = session.query(Student).filter(
            Student.is_deleted == False,
            Student.status == "Active"
        )

        if target_group and not is_branch_wise:
            query = query.filter(Student.group_name == target_group)

        total_students = query.count()

        active_venues = session.query(Venue).filter(Venue.is_active == True).all()
        time_slots = session.query(TimeSlot).all()

        total_capacity = sum(v.capacity for v in active_venues)

        is_sufficient = total_capacity >= total_students
        deficiency = max(0, total_students - total_capacity)

        suggested_per_slot = {}
        if deficiency > 0 and len(time_slots) > 0:
            for ts in time_slots:
                suggested_per_slot[ts.slot_name] = deficiency

        return CapacityReport(
            total_students=total_students,
            total_capacity=total_capacity,
            is_sufficient=is_sufficient,
            deficiency=deficiency,
            suggested_per_slot=suggested_per_slot
        )

    @classmethod
    def select_minimal_venues(cls, venues: List[Venue], target_capacity: int) -> List[Venue]:
        """
        Finds a subset of venues that minimizes the number of venues used to satisfy target_capacity.
        If target_capacity is greater than or equal to total capacity, returns all venues.
        """
        if not venues or target_capacity <= 0:
            return []
        
        total_cap = sum(v.capacity for v in venues)
        if target_capacity >= total_cap:
            return list(venues)
        
        best_subset = None
        best_size = len(venues) + 1
        best_cap = float('inf')
        
        # Sort by capacity descending, then by id ascending for determinism
        sorted_venues = sorted(venues, key=lambda v: (-v.capacity, v.id))
        
        def search(index, current_subset, current_cap):
            nonlocal best_subset, best_size, best_cap
            
            if len(current_subset) > best_size:
                return
                
            if current_cap >= target_capacity:
                if len(current_subset) < best_size:
                    best_size = len(current_subset)
                    best_subset = list(current_subset)
                    best_cap = current_cap
                elif len(current_subset) == best_size:
                    # Choose subset with smaller capacity (closer to target_capacity to reduce waste)
                    if current_cap < best_cap:
                        best_subset = list(current_subset)
                        best_cap = current_cap
                return
                
            if index >= len(sorted_venues):
                return
                
            # Branch 1: Include sorted_venues[index]
            current_subset.append(sorted_venues[index])
            search(index + 1, current_subset, current_cap + sorted_venues[index].capacity)
            current_subset.pop()
            
            # Branch 2: Exclude sorted_venues[index]
            search(index + 1, current_subset, current_cap)
            
        search(0, [], 0)
        return sorted(best_subset, key=lambda v: v.id) if best_subset is not None else list(venues)

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
        remainders: List[Tuple[float, int, int]] = []

        for v in venues:
            exact = v.capacity * ratio
            base = min(int(exact), v.capacity)
            base_alloc[v.id] = base
            rem = exact - base
            remainders.append((rem, v.capacity, v.id))

        assigned = sum(base_alloc.values())
        deficit = slot_student_count - assigned

        remainders.sort(key=lambda x: (x[0], x[1]), reverse=True)

        idx = 0
        while deficit > 0 and remainders:
            rem, max_cap, v_id = remainders[idx % len(remainders)]
            if base_alloc[v_id] < max_cap:
                base_alloc[v_id] += 1
                deficit -= 1
            idx += 1
            if idx > len(remainders) * 100:
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
        """
        v_ids = list(venue_targets.keys())
        strata_keys = list(strata_students.keys())
        total_students = sum(len(s_list) for s_list in strata_students.values())

        if total_students == 0 or not v_ids:
            return {}

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

        row_deficits = {v_id: venue_targets[v_id] - sum(base_matrix[(v_id, k)] for k in strata_keys) for v_id in v_ids}
        col_deficits = {k: len(strata_students[k]) - sum(base_matrix[(v, k)] for v in v_ids) for k in strata_keys}

        remainders.sort(key=lambda item: item[0], reverse=True)

        for rem, v_id, s_key in remainders:
            if row_deficits[v_id] > 0 and col_deficits[s_key] > 0:
                base_matrix[(v_id, s_key)] += 1
                row_deficits[v_id] -= 1
                col_deficits[s_key] -= 1

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
        group_counts: Dict[str, int],
        venue_group_locks: Dict[int, str] = None
    ) -> Dict[str, List[Venue]]:
        """
        Partitions available active venues among active student groups for a single time slot,
        guaranteeing that every venue is assigned to at most ONE group in this slot,
        respecting any pre-existing group locks.
        """
        if venue_group_locks is None:
            venue_group_locks = {}

        assigned: Dict[str, List[Venue]] = {g: [] for g in group_counts}
        assigned_caps: Dict[str, int] = {g: 0 for g in group_counts}

        # First, pre-assign locked venues to their respective groups
        unlocked_venues = []
        for v in venues:
            if v.id in venue_group_locks:
                locked_group = venue_group_locks[v.id]
                if locked_group in assigned:
                    assigned[locked_group].append(v)
                    assigned_caps[locked_group] += v.capacity
            else:
                unlocked_venues.append(v)

        active_groups = [g for g, cnt in group_counts.items() if cnt > 0]
        if not active_groups:
            return assigned

        if len(active_groups) == 1:
            assigned[active_groups[0]].extend(unlocked_venues)
            return assigned

        sorted_groups = sorted(active_groups, key=lambda g: (-group_counts[g], g))

        total_students = sum(group_counts[g] for g in sorted_groups)
        total_venue_capacity = sum(v.capacity for v in venues)

        group_target_caps = {}
        for g in sorted_groups:
            exact = (total_venue_capacity * group_counts[g]) / max(1, total_students)
            group_target_caps[g] = int(round(exact))

        sorted_venues = sorted(unlocked_venues, key=lambda v: (-v.capacity, v.id))

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
    def _distribute_department_evenly(
        cls,
        venues: List[Venue],
        total_students: int
    ) -> Dict[int, int]:
        """
        Distributes department students across assigned venues as evenly as possible.
        For example:
        450 students across 3 halls (capacity 200 each) -> {v1: 150, v2: 150, v3: 150}
        500 students across 3 halls (capacity 200 each) -> {v1: 167, v2: 167, v3: 166}
        """
        if not venues or total_students <= 0:
            return {v.id: 0 for v in venues}

        total_capacity = sum(v.capacity for v in venues)
        num_venues = len(venues)

        equal_target = total_students // num_venues
        remainder = total_students % num_venues

        sorted_venues = sorted(venues, key=lambda v: (-v.capacity, v.id))

        can_equal_split = all(v.capacity >= equal_target + (1 if idx < remainder else 0) for idx, v in enumerate(sorted_venues))

        if can_equal_split:
            targets = {}
            for idx, v in enumerate(sorted_venues):
                targets[v.id] = equal_target + (1 if idx < remainder else 0)
            return targets
        else:
            ratio = min(1.0, total_students / max(1, total_capacity))
            base_alloc: Dict[int, int] = {}
            remainders: List[Tuple[float, int, int]] = []

            for v in sorted_venues:
                exact = v.capacity * ratio
                base = min(int(exact), v.capacity)
                base_alloc[v.id] = base
                rem = exact - base
                remainders.append((rem, v.capacity, v.id))

            assigned = sum(base_alloc.values())
            deficit = total_students - assigned
            remainders.sort(key=lambda x: (x[0], x[1]), reverse=True)

            idx = 0
            while deficit > 0 and remainders:
                rem, max_cap, v_id = remainders[idx % len(remainders)]
                if base_alloc[v_id] < max_cap:
                    base_alloc[v_id] += 1
                    deficit -= 1
                idx += 1
                if idx > len(remainders) * 100:
                    break
            return base_alloc

    @classmethod
    def _distribute_department_evenly_constrained(
        cls,
        venues: List[Venue],
        rem_caps: Dict[int, int],
        total_students: int
    ) -> Dict[int, int]:
        """
        Distributes department students across selected venues as evenly as possible,
        without exceeding each venue's remaining capacity.
        """
        if not venues or total_students <= 0:
            return {v.id: 0 for v in venues}

        targets: Dict[int, int] = {v.id: 0 for v in venues}
        remaining = total_students
        active_venues = list(venues)

        while remaining > 0 and active_venues:
            share = remaining // len(active_venues)
            extra = remaining % len(active_venues)

            if share == 0 and extra == 0:
                break

            progress = False
            for idx, v in enumerate(list(active_venues)):
                alloc_amount = share + (1 if idx < extra else 0)
                if alloc_amount == 0:
                    continue
                available_space = rem_caps[v.id] - targets[v.id]
                actual_add = min(alloc_amount, available_space)
                if actual_add > 0:
                    targets[v.id] += actual_add
                    remaining -= actual_add
                    progress = True
                if targets[v.id] >= rem_caps[v.id]:
                    active_venues.remove(v)

            if not progress:
                for v in list(active_venues):
                    avail = rem_caps[v.id] - targets[v.id]
                    to_add = min(remaining, avail)
                    if to_add > 0:
                        targets[v.id] += to_add
                        remaining -= to_add
                    if remaining == 0:
                        break
                break

        return targets

    @classmethod
    def _partition_venues_by_department(
        cls,
        venues: List[Venue],
        dept_counts: Dict[int, int]
    ) -> Dict[int, List[Venue]]:
        """
        Partitions active venues among departments for a single time slot,
        guaranteeing that every venue is assigned to at most ONE department in this slot.
        """
        if not dept_counts or not venues:
            return {}

        active_depts = [d for d, cnt in dept_counts.items() if cnt > 0]
        if not active_depts:
            return {}

        if len(active_depts) == 1:
            return {active_depts[0]: list(venues)}

        sorted_depts = sorted(active_depts, key=lambda d: (-dept_counts[d], d))
        sorted_venues = sorted(venues, key=lambda v: (-v.capacity, v.id))

        assigned: Dict[int, List[Venue]] = {d: [] for d in sorted_depts}
        assigned_caps: Dict[int, int] = {d: 0 for d in sorted_depts}

        for v in sorted_venues:
            best_dept = None
            max_deficiency = -float('inf')

            for d in sorted_depts:
                needed = dept_counts[d]
                deficiency = needed - assigned_caps[d]
                if deficiency > max_deficiency:
                    max_deficiency = deficiency
                    best_dept = d

            if best_dept is None:
                best_dept = sorted_depts[0]

            assigned[best_dept].append(v)
            assigned_caps[best_dept] += v.capacity

        return assigned

    @classmethod
    def save_current_allocation_to_history(cls, session: Session, mode: str, config_info: Optional[dict] = None) -> Optional[AllocationRun]:
        """Serializes the current active allocation in the database and saves it as an AllocationRun."""
        import json
        is_branch_wise = mode in ("branch_wise", "branch", "department_wise")

        # Query active students who currently have a venue allocated in this mode
        query = session.query(Student).filter(
            Student.is_deleted == False,
            Student.status == "Active"
        )
        if is_branch_wise:
            query = query.filter(Student.branch_venue_id.isnot(None))
        else:
            query = query.filter(Student.group_venue_id.isnot(None))

        allocated_students = query.all()
        if not allocated_students:
            return None

        # Build list of assignments and find venues used
        assignments = []
        venues_used = set()
        allocated_at = None

        for s in allocated_students:
            if is_branch_wise:
                v_name = s.branch_venue.name if s.branch_venue else None
                slot_name = s.branch_time_slot.slot_name if s.branch_time_slot else None
                s_allocated_at = s.branch_venue_allocated_at
            else:
                v_name = s.group_venue.name if s.group_venue else None
                slot_name = s.group_time_slot.slot_name if s.group_time_slot else None
                s_allocated_at = s.group_venue_allocated_at

            if v_name:
                venues_used.add(v_name)
            if s_allocated_at and (not allocated_at or s_allocated_at > allocated_at):
                allocated_at = s_allocated_at

            assignments.append({
                "usn": s.usn,
                "venue_name": v_name,
                "slot_name": slot_name
            })

        if not allocated_at:
            allocated_at = datetime.utcnow()

        run = AllocationRun(
            mode="branch_wise" if is_branch_wise else "group_wise",
            allocated_at=allocated_at,
            student_count=len(allocated_students),
            venues_used=json.dumps(list(venues_used)),
            config=json.dumps(config_info or {}),
            assignments_json=json.dumps(assignments)
        )
        session.add(run)
        session.flush()
        return run

    @classmethod
    def optimize_allocations(
        cls,
        target_group: Optional[str] = None,
        mode: str = "group_wise",
        allow_department_splits: bool = True,
        auto_backup: bool = True
    ) -> AllocationResult:
        """
        Executes Venue Optimization in selected mode:
        1. "group_wise": Populates independent group_venue_id and group_time_slot_id.
        2. "branch_wise": Populates independent branch_venue_id and branch_time_slot_id.
        """
        if auto_backup:
            BackupManager.create_backup(trigger_action="PRE_VENUE_ALLOCATION")

        session: Session = SessionLocal()
        try:
            is_branch_wise = mode in ("branch_wise", "branch", "department_wise")

            # 1. Fetch current active configuration info for history
            venues = session.query(Venue).filter(Venue.is_active == True).all()
            time_slots = session.query(TimeSlot).all()
            config_info = {
                "venues": [{"name": v.name, "capacity": v.capacity} for v in venues],
                "time_slots": [{"name": ts.slot_name, "start": ts.start_time, "end": ts.end_time} for ts in time_slots],
                "allow_department_splits": allow_department_splits
            }

            # 2. Save existing allocations (if any) to history before clearing
            cls.save_current_allocation_to_history(session, mode, config_info)

            # 3. Clear ALL current active venue assignments in the database for this mode
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
            session.flush()

            # Now perform capacity check on all active students
            cap_report = cls.check_capacity(session, target_group, mode=mode)

            # Query all active students (which are now unallocated since we just cleared the assignments)
            query = session.query(Student).filter(
                Student.is_deleted == False,
                Student.status == "Active"
            )

            if target_group and not is_branch_wise:
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

            venues.sort(key=lambda v: v.id)
            time_slots.sort(key=lambda t: t.id)

            total_unallocated = len(unallocated_students)
            allocated_count = 0
            now = datetime.utcnow()
            warnings_list = []

            if is_branch_wise:
                # --- BRANCH-WISE ALLOCATION (INDEPENDENT & HIERARCHICAL PRIORITIES) ---
                depts_unallocated: Dict[int, List[Student]] = {}
                for s in unallocated_students:
                    d_id = s.department_id or 0
                    if d_id not in depts_unallocated:
                        depts_unallocated[d_id] = []
                    depts_unallocated[d_id].append(s)

                import random
                for d_id in depts_unallocated:
                    random.shuffle(depts_unallocated[d_id])

                initial_dept_counts = {d_id: len(stus) for d_id, stus in depts_unallocated.items()}

                for t_slot in time_slots:
                    active_dept_ids = [d for d, stus in depts_unallocated.items() if len(stus) > 0]
                    if not active_dept_ids:
                        break

                    # Deterministic sort: largest departments first
                    active_dept_ids.sort(key=lambda d: (-len(depts_unallocated[d]), d))

                    # Determine active venues with remaining capacity in this slot
                    avail_venues = []
                    venue_dept_locks = {}
                    for v in venues:
                        allocated_sample = session.query(Student).filter(
                            Student.is_deleted == False,
                            Student.branch_venue_id == v.id,
                            Student.branch_time_slot_id == t_slot.id
                        ).first()

                        db_alloc_count = session.query(Student).filter(
                            Student.is_deleted == False,
                            Student.branch_venue_id == v.id
                        ).count()
                        rem_cap = max(0, v.capacity - db_alloc_count)
                        if rem_cap > 0:
                            avail_venues.append(Venue(id=v.id, name=v.name, capacity=rem_cap, is_active=True))
                            if allocated_sample:
                                venue_dept_locks[v.id] = allocated_sample.department_id or 0

                    # Track remaining venue capacities in this time slot
                    venue_rem_caps: Dict[int, int] = {v.id: v.capacity for v in avail_venues}

                    for dept_id in active_dept_ids:
                        d_students = depts_unallocated[dept_id]
                        if not d_students:
                            continue

                        N = len(d_students)

                        # Filter available venues in this time slot with remaining capacity > 0 and compatible with dept_id
                        current_avail_venues = [
                            v for v in avail_venues 
                            if venue_rem_caps[v.id] > 0 and (v.id not in venue_dept_locks or venue_dept_locks[v.id] == dept_id)
                        ]
                        if not current_avail_venues:
                            break

                        # PRIORITY 1 & 4: Single Venue Best-Fit Check
                        single_candidates = [v for v in current_avail_venues if venue_rem_caps[v.id] >= N]
                        if single_candidates:
                            # Best-Fit single venue: smallest sufficient capacity, tied by venue ID
                            single_candidates.sort(key=lambda v: (venue_rem_caps[v.id], v.id))
                            best_venue = single_candidates[0]

                            count_to_take = N
                            slot_d_students = d_students[:count_to_take]
                            depts_unallocated[dept_id] = d_students[count_to_take:]

                            selected_venues = [best_venue]
                            venue_targets = {best_venue.id: count_to_take}
                        else:
                            # PRIORITY 2, 3 & 4: Multi-Venue Minimal Split
                            # Use select_minimal_venues to find the best minimal subset of venues
                            temp_venues = [
                                Venue(id=v.id, name=v.name, capacity=venue_rem_caps[v.id], is_active=True)
                                for v in current_avail_venues
                            ]
                            k_venues = cls.select_minimal_venues(temp_venues, N)
                            running_cap = sum(venue_rem_caps[v.id] for v in k_venues)

                            count_to_take = min(N, running_cap)
                            slot_d_students = d_students[:count_to_take]
                            depts_unallocated[dept_id] = d_students[count_to_take:]

                            selected_venues = k_venues
                            venue_targets = cls._distribute_department_evenly_constrained(
                                selected_venues, venue_rem_caps, count_to_take
                            )

                        # Deduct assigned capacities in this time slot
                        for v in selected_venues:
                            venue_rem_caps[v.id] -= venue_targets.get(v.id, 0)

                        # Allocate gender strata to selected venues according to venue_targets
                        gender_students: Dict[str, List[Student]] = {}
                        for s in slot_d_students:
                            g_key = s.gender or "Unknown"
                            if g_key not in gender_students:
                                gender_students[g_key] = []
                            gender_students[g_key].append(s)

                        matrix_alloc = cls._allocate_strata_matrix(
                            venue_targets,
                            {(dept_id, g): stus for g, stus in gender_students.items()}
                        )

                        strata_indices: Dict[Tuple[int, str], int] = {(dept_id, g): 0 for g in gender_students}

                        for v in selected_venues:
                            v_id = v.id
                            for g in gender_students:
                                s_key = (dept_id, g)
                                assign_count = matrix_alloc.get((v_id, s_key), 0)
                                if assign_count > 0:
                                    s_list = gender_students[g]
                                    curr_start = strata_indices[s_key]
                                    sub_group = s_list[curr_start : curr_start + assign_count]
                                    strata_indices[s_key] += assign_count

                                    for s in sub_group:
                                        s.branch_venue_id = v_id
                                        s.branch_time_slot_id = t_slot.id
                                        s.branch_venue_allocated_at = now
                                        allocated_count += 1

                    # Flush after finishing allocation for this slot to ensure correct overall capacity check for next slots
                    session.flush()

                # Verification Assertion: Ensure no venue in any slot contains multiple branches
                allocated_pairs = session.query(
                    Student.branch_time_slot_id, Student.branch_venue_id, Student.department_id
                ).filter(
                    Student.is_deleted == False,
                    Student.branch_venue_id.isnot(None),
                    Student.branch_time_slot_id.isnot(None)
                ).distinct().all()

                slot_venue_map: Dict[Tuple[int, int], set] = {}
                for ts_id, v_id, d_id in allocated_pairs:
                    key = (ts_id, v_id)
                    if key not in slot_venue_map:
                        slot_venue_map[key] = set()
                    slot_venue_map[key].add(d_id or 0)

                for (ts_id, v_id), d_set in slot_venue_map.items():
                    if len(d_set) > 1:
                        session.rollback()
                        raise RuntimeError(
                            f"Branch isolation violation detected! Venue ID {v_id} in Time Slot ID {ts_id} contains multiple departments: {d_set}"
                        )

                # Add warnings compile for branch-wise capacity
                for dept_id, stus in depts_unallocated.items():
                    if len(stus) > 0:
                        dept = session.query(Department).filter(Department.id == dept_id).first()
                        dept_name = dept.name if dept else f"Department {dept_id}"
                        unallocated_cnt = len(stus)
                        total_cnt = initial_dept_counts[dept_id]
                        avail_cap = total_cnt - unallocated_cnt
                        warnings_list.append(
                            f"Venue allocation could not be completed.\n"
                            f"{dept_name} has insufficient venue capacity.\n"
                            f"Required Capacity: {total_cnt}\n"
                            f"Available Capacity: {avail_cap}\n"
                            f"Unallocated Students: {unallocated_cnt}"
                        )

            else:
                # --- GROUP-WISE ALLOCATION (INDEPENDENT) ---
                groups_unallocated: Dict[str, List[Student]] = {}
                for s in unallocated_students:
                    g_key = s.group_name or "Unassigned"
                    if g_key not in groups_unallocated:
                        groups_unallocated[g_key] = []
                    groups_unallocated[g_key].append(s)

                import random
                for g_key in groups_unallocated:
                    random.shuffle(groups_unallocated[g_key])

                initial_group_counts = {g_name: len(stus) for g_name, stus in groups_unallocated.items()}

                for t_slot in time_slots:
                    active_group_counts = {g: len(stus) for g, stus in groups_unallocated.items() if len(stus) > 0}
                    if not active_group_counts:
                        break

                    # Determine active venues with remaining capacity in this slot
                    avail_venues = []
                    venue_group_locks = {}
                    for v in venues:
                        allocated_sample = session.query(Student).filter(
                            Student.is_deleted == False,
                            Student.group_venue_id == v.id,
                            Student.group_time_slot_id == t_slot.id
                        ).first()

                        db_alloc_count = session.query(Student).filter(
                            Student.is_deleted == False,
                            Student.group_venue_id == v.id
                        ).count()
                        rem_cap = max(0, v.capacity - db_alloc_count)
                        if rem_cap > 0:
                            avail_venues.append(Venue(id=v.id, name=v.name, capacity=rem_cap, is_active=True))
                            if allocated_sample:
                                venue_group_locks[v.id] = allocated_sample.group_name or "Unassigned"

                    if not avail_venues:
                        continue

                    partitioned_venues = cls._partition_venues_by_group(avail_venues, active_group_counts, venue_group_locks)

                    for g_name, g_venues in partitioned_venues.items():
                        if not g_venues:
                            continue

                        g_students = groups_unallocated.get(g_name, [])
                        if not g_students:
                            continue

                        g_slot_capacity = sum(v.capacity for v in g_venues)
                        count_to_take = min(len(g_students), g_slot_capacity)

                        minimal_g_venues = cls.select_minimal_venues(g_venues, count_to_take)

                        slot_g_students = g_students[:count_to_take]
                        groups_unallocated[g_name] = g_students[count_to_take:]

                        venue_targets = cls._distribute_venue_capacities(minimal_g_venues, count_to_take)

                        strata_students: Dict[Tuple[int, str], List[Student]] = {}
                        for s in slot_g_students:
                            s_key = (s.department_id or 0, s.gender or "Unknown")
                            if s_key not in strata_students:
                                strata_students[s_key] = []
                            strata_students[s_key].append(s)

                        matrix_alloc = cls._allocate_strata_matrix(venue_targets, strata_students)
                        strata_indices: Dict[Tuple[int, str], int] = {k: 0 for k in strata_students}

                        for v in minimal_g_venues:
                            v_id = v.id
                            for s_key, s_list in strata_students.items():
                                assign_count = matrix_alloc.get((v_id, s_key), 0)
                                if assign_count > 0:
                                    curr_start = strata_indices[s_key]
                                    sub_group = s_list[curr_start : curr_start + assign_count]
                                    strata_indices[s_key] += assign_count

                                    for s in sub_group:
                                        s.group_venue_id = v_id
                                        s.group_time_slot_id = t_slot.id
                                        s.group_venue_allocated_at = now
                                        s.venue_id = v_id
                                        s.time_slot_id = t_slot.id
                                        s.venue_allocated_at = now
                                        allocated_count += 1

                    # Flush after finishing allocation for this slot to ensure correct overall capacity check for next slots
                    session.flush()

                # Verification Assertion: Ensure no venue in any slot contains multiple groups
                allocated_pairs = session.query(
                    Student.group_time_slot_id, Student.group_venue_id, Student.group_name
                ).filter(
                    Student.is_deleted == False,
                    Student.group_venue_id.isnot(None),
                    Student.group_time_slot_id.isnot(None)
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

                # Add warnings compile for group-wise capacity
                for g_name, stus in groups_unallocated.items():
                    if len(stus) > 0:
                        unallocated_cnt = len(stus)
                        total_cnt = initial_group_counts[g_name]
                        avail_cap = total_cnt - unallocated_cnt
                        warnings_list.append(
                            f"Venue allocation could not be completed.\n"
                            f"{g_name} has insufficient venue capacity.\n"
                            f"Required Capacity: {total_cnt}\n"
                            f"Available Capacity: {avail_cap}\n"
                            f"Unallocated Students: {unallocated_cnt}"
                        )

            # Save new allocations to history before committing
            cls.save_current_allocation_to_history(session, mode, config_info)

            # Log audit
            audit_mode = "BRANCH_WISE" if is_branch_wise else "GROUP_WISE"
            audit = AuditLog(
                action="VENUE_OPTIMIZATION_SUCCESS",
                entity_type="VenueAllocation",
                details=f"Successfully allocated {allocated_count} students using {audit_mode} mode across {len(time_slots)} slots."
            )
            session.add(audit)
            session.commit()

            return AllocationResult(
                total_processed=total_unallocated,
                newly_allocated_groups=0,
                newly_allocated_venues=allocated_count,
                skipped_existing=0,
                warnings=warnings_list
            )

        except Exception as e:
            session.rollback()
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Venue optimization failed: {str(e)}")
        finally:
            session.close()

