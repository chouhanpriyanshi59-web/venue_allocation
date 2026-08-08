from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QDialog, QDialogButtonBox, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from database.connection import SessionLocal
from database.models import Venue, TimeSlot, Department, Student
from database.repository import Repository
from engine.venue_optimizer import VenueOptimizer

class BranchVenueAllocationView(QWidget):
    branch_allocation_done = Signal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Title
        lbl_header = QLabel("Branch-wise Venue Allocation")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC;")
        layout.addWidget(lbl_header)

        # Capacity Banner Card
        self.diag_card = QFrame()
        self.diag_card.setProperty("class", "card-widget")
        dc_layout = QVBoxLayout(self.diag_card)

        self.lbl_cap_status = QLabel("Checking venue capacities...")
        self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #38BDF8;")

        self.lbl_cap_details = QLabel("")
        self.lbl_cap_details.setStyleSheet("color: #94A3B8;")

        dc_layout.addWidget(self.lbl_cap_status)
        dc_layout.addWidget(self.lbl_cap_details)
        layout.addWidget(self.diag_card)

        # Main Split: Departments Overview + Venues/Slots
        main_split = QHBoxLayout()

        # Department Strength Table Box
        dept_box = QFrame()
        dept_box.setProperty("class", "card-widget")
        db_layout = QVBoxLayout(dept_box)

        lbl_d_title = QLabel("Department Strengths & Branch Allocation")
        lbl_d_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        db_layout.addWidget(lbl_d_title)

        self.dept_table = QTableWidget(0, 4)
        self.dept_table.setHorizontalHeaderLabels(["Department Name", "Code", "Student Count", "Allocated Venues"])
        self.dept_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        db_layout.addWidget(self.dept_table)

        main_split.addWidget(dept_box, stretch=1)

        # Venues & Time Slots Box
        config_box = QFrame()
        config_box.setProperty("class", "card-widget")
        cb_layout = QVBoxLayout(config_box)

        lbl_v_title = QLabel("Configured Active Venues & Time Slots")
        lbl_v_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        cb_layout.addWidget(lbl_v_title)

        self.venue_summary_table = QTableWidget(0, 3)
        self.venue_summary_table.setHorizontalHeaderLabels(["Venue Name", "Capacity", "Status"])
        self.venue_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cb_layout.addWidget(self.venue_summary_table)

        main_split.addWidget(config_box, stretch=1)
        layout.addLayout(main_split)

        # Footer Action Card
        footer_card = QFrame()
        footer_card.setProperty("class", "card-widget")
        footer_layout = QHBoxLayout(footer_card)

        lbl_desc = QLabel("Branch-wise mode allocates every department to dedicated venues independently.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")

        btn_run_branch = QPushButton("Allocate Branch-wise Venues")
        btn_run_branch.setProperty("class", "primary-btn")
        btn_run_branch.setStyleSheet("padding: 8px 20px; font-weight: bold; font-size: 13px; background-color: #8B5CF6;")
        btn_run_branch.clicked.connect(self.run_branch_allocation)

        footer_layout.addWidget(lbl_desc)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_run_branch)
        layout.addWidget(footer_card)

        self.refresh_tables()

    def refresh_tables(self):
        session = SessionLocal()
        try:
            # 1. Department Strengths & Allocation Status
            depts = session.query(Department).all()
            self.dept_table.setRowCount(0)
            for d in depts:
                stus = session.query(Student).filter(
                    Student.is_deleted == False,
                    Student.status == "Active",
                    Student.department_id == d.id
                ).all()
                total_cnt = len(stus)
                allocated_cnt = len([s for s in stus if s.branch_venue_id is not None])

                row = self.dept_table.rowCount()
                self.dept_table.insertRow(row)
                self.dept_table.setItem(row, 0, QTableWidgetItem(d.name))
                self.dept_table.setItem(row, 1, QTableWidgetItem(d.code))
                self.dept_table.setItem(row, 2, QTableWidgetItem(str(total_cnt)))

                status_str = f"{allocated_cnt}/{total_cnt} Allocated" if total_cnt > 0 else "No Students"
                self.dept_table.setItem(row, 3, QTableWidgetItem(status_str))

            # 2. Venue Table Summary
            venues = session.query(Venue).all()
            self.venue_summary_table.setRowCount(0)
            for v in venues:
                row = self.venue_summary_table.rowCount()
                self.venue_summary_table.insertRow(row)
                self.venue_summary_table.setItem(row, 0, QTableWidgetItem(v.name))
                self.venue_summary_table.setItem(row, 1, QTableWidgetItem(str(v.capacity)))
                self.venue_summary_table.setItem(row, 2, QTableWidgetItem("Active" if v.is_active else "Inactive"))

            # 3. Capacity Report
            cap_report = VenueOptimizer.check_capacity(session, mode="branch_wise")
            if cap_report.is_sufficient:
                self.lbl_cap_status.setText("Branch Capacity Check Passed ✓")
                self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981;")
                self.lbl_cap_details.setText(
                    f"Total unassigned branch students: {cap_report.total_students:,} | Total venue capacity available: {cap_report.total_capacity:,}."
                )
            else:
                self.lbl_cap_status.setText("WARNING: Insufficient Venue Capacity! ⚠️")
                self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #EF4444;")
                self.lbl_cap_details.setText(
                    f"Required: {cap_report.total_students:,} | Available: {cap_report.total_capacity:,} | Deficit: {cap_report.deficiency} seats."
                )
        finally:
            session.close()

    def run_branch_allocation(self):
        try:
            res = VenueOptimizer.optimize_allocations(mode="branch_wise")
            if res.warnings and any("insufficient venue capacity" in w for w in res.warnings):
                warning_text = "\n\n---\n\n".join(res.warnings)
                QMessageBox.warning(
                    self,
                    "Insufficient Venue Capacity",
                    warning_text
                )
            else:
                QMessageBox.information(
                    self,
                    "Branch-wise Venue Allocation Complete",
                    f"Successfully completed Branch-wise Venue Allocation!\n\n"
                    f"Assigned {res.newly_allocated_venues} students to dedicated department venues."
                )
            self.refresh_tables()
            self.branch_allocation_done.emit()
        except Exception as e:
            QMessageBox.critical(self, "Branch Optimization Error", str(e))
