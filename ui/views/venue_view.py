from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal
from database.connection import SessionLocal
from database.models import Venue, TimeSlot
from database.repository import Repository
from engine.venue_optimizer import VenueOptimizer
from core.exceptions import CapacityExceededError

class VenueAllocationView(QWidget):
    venue_allocation_done = Signal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Diagnostics & Capacity Check Banner Card
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

        # Venues & Time Slots Split Layout
        lists_layout = QHBoxLayout()

        # Venues Table Box
        venue_box = QFrame()
        venue_box.setProperty("class", "card-widget")
        vb_layout = QVBoxLayout(venue_box)

        v_head = QHBoxLayout()
        lbl_v_title = QLabel("Configured Venues")
        lbl_v_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        
        btn_add_v = QPushButton("+ Add Venue")
        btn_add_v.setProperty("class", "secondary-btn")
        btn_add_v.clicked.connect(self.add_venue)
        
        v_head.addWidget(lbl_v_title)
        v_head.addStretch()
        v_head.addWidget(btn_add_v)
        vb_layout.addLayout(v_head)

        self.venue_table = QTableWidget(0, 4)
        self.venue_table.setHorizontalHeaderLabels(["Venue Name", "Capacity", "Status", "Action"])
        self.venue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.venue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        vb_layout.addWidget(self.venue_table)

        lists_layout.addWidget(venue_box)

        # Time Slots Table Box
        slot_box = QFrame()
        slot_box.setProperty("class", "card-widget")
        sb_layout = QVBoxLayout(slot_box)

        s_head = QHBoxLayout()
        lbl_s_title = QLabel("Configured Time Slots")
        lbl_s_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")

        btn_add_s = QPushButton("+ Add Time Slot")
        btn_add_s.setProperty("class", "secondary-btn")
        btn_add_s.clicked.connect(self.add_timeslot)

        s_head.addWidget(lbl_s_title)
        s_head.addStretch()
        s_head.addWidget(btn_add_s)
        sb_layout.addLayout(s_head)

        self.slot_table = QTableWidget(0, 4)
        self.slot_table.setHorizontalHeaderLabels(["Slot Name", "Start Time", "End Time", "Action"])
        self.slot_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slot_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        sb_layout.addWidget(self.slot_table)

        lists_layout.addWidget(slot_box)
        layout.addLayout(lists_layout)

        # Execute Optimization Footer Card
        footer_card = QFrame()
        footer_card.setProperty("class", "card-widget")
        footer_layout = QHBoxLayout(footer_card)

        lbl_mode = QLabel("Allocation Mode:")
        lbl_mode.setStyleSheet("font-size: 13px; font-weight: bold; color: #F8FAFC;")

        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Group-wise Allocation (Group A / Group B)",
            "Branch-wise Allocation (Department-wise)"
        ])
        self.combo_mode.setMinimumWidth(280)
        self.combo_mode.setStyleSheet(
            "QComboBox { background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 13px; font-weight: bold; }"
            "QComboBox::drop-down { border: 0px; }"
            "QComboBox QAbstractItemView { background-color: #1E293B; color: #F8FAFC; selection-background-color: #3B82F6; }"
        )

        btn_run_milp = QPushButton("Allocate Venues")
        btn_run_milp.setProperty("class", "primary-btn")
        btn_run_milp.setStyleSheet("padding: 8px 20px; font-weight: bold; font-size: 13px;")
        btn_run_milp.clicked.connect(self.run_optimization)

        footer_layout.addWidget(lbl_mode)
        footer_layout.addWidget(self.combo_mode)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_run_milp)
        layout.addWidget(footer_card)

        self.refresh_tables()

    def refresh_tables(self):
        session = SessionLocal()
        try:
            # Refresh Venues
            venues = session.query(Venue).all()
            self.venue_table.setRowCount(0)
            for v in venues:
                row = self.venue_table.rowCount()
                self.venue_table.insertRow(row)
                self.venue_table.setItem(row, 0, QTableWidgetItem(v.name))
                self.venue_table.setItem(row, 1, QTableWidgetItem(str(v.capacity)))
                self.venue_table.setItem(row, 2, QTableWidgetItem("Active" if v.is_active else "Inactive"))

                btn_del_v = QPushButton("Remove")
                btn_del_v.setProperty("class", "danger-btn")
                btn_del_v.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_del_v.clicked.connect(lambda checked=False, vid=v.id, vname=v.name: self.delete_venue(vid, vname))
                self.venue_table.setCellWidget(row, 3, btn_del_v)

            # Refresh Time Slots
            slots = session.query(TimeSlot).all()
            self.slot_table.setRowCount(0)
            for s in slots:
                row = self.slot_table.rowCount()
                self.slot_table.insertRow(row)
                self.slot_table.setItem(row, 0, QTableWidgetItem(s.slot_name))
                self.slot_table.setItem(row, 1, QTableWidgetItem(s.start_time))
                self.slot_table.setItem(row, 2, QTableWidgetItem(s.end_time))

                btn_del_s = QPushButton("Remove")
                btn_del_s.setProperty("class", "danger-btn")
                btn_del_s.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_del_s.clicked.connect(lambda checked=False, sid=s.id, sname=s.slot_name: self.delete_timeslot(sid, sname))
                self.slot_table.setCellWidget(row, 3, btn_del_s)

            # Capacity Report
            cap_report = VenueOptimizer.check_capacity(session)
            if cap_report.is_sufficient:
                self.lbl_cap_status.setText("Capacity Check Passed ✓")
                self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981;")
                self.lbl_cap_details.setText(
                    f"Total unassigned students: {cap_report.total_students:,} | Total venue capacity available across slots: {cap_report.total_capacity:,}."
                )
            else:
                self.lbl_cap_status.setText("WARNING: Insufficient Venue Capacity! ⚠️")
                self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #EF4444;")
                sug_str = ", ".join([f"{k}: +{v}" for k, v in cap_report.suggested_per_slot.items()])
                self.lbl_cap_details.setText(
                    f"Required: {cap_report.total_students:,} | Available: {cap_report.total_capacity:,} | Deficit: {cap_report.deficiency} seats.\n"
                    f"Suggested Capacity Increase: Add at least {sug_str} seats."
                )
        finally:
            session.close()

    def add_venue(self):
        name, ok1 = QInputDialog.getText(self, "Add New Venue", "Venue Name (e.g. Auditorium A):")
        if ok1 and name.strip():
            cap, ok2 = QInputDialog.getInt(self, "Venue Capacity", f"Capacity for '{name.strip()}':", 200, 10, 5000)
            if ok2:
                session = SessionLocal()
                try:
                    Repository.get_or_create_venue(session, name.strip(), cap)
                    session.commit()
                    self.refresh_tables()
                    self.venue_allocation_done.emit()
                finally:
                    session.close()

    def delete_venue(self, venue_id: int, venue_name: str):
        reply = QMessageBox.question(
            self,
            "Confirm Remove Venue",
            f"Are you sure you want to remove the venue '{venue_name}'?\n\n"
            "Any students currently assigned to this venue will have their venue allocation reset.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            session = SessionLocal()
            try:
                ok, msg = Repository.delete_venue(session, venue_id)
                if ok:
                    self.refresh_tables()
                    self.venue_allocation_done.emit()
                else:
                    QMessageBox.warning(self, "Error", msg)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete venue: {str(e)}")
            finally:
                session.close()

    def add_timeslot(self):
        name, ok1 = QInputDialog.getText(self, "Add Time Slot", "Slot Name (e.g. Morning Session):")
        if ok1 and name.strip():
            start, ok2 = QInputDialog.getText(self, "Start Time", "Start Time (e.g. 09:30 AM):")
            if ok2 and start.strip():
                end, ok3 = QInputDialog.getText(self, "End Time", "End Time (e.g. 11:30 AM):")
                if ok3 and end.strip():
                    session = SessionLocal()
                    try:
                        Repository.get_or_create_time_slot(session, name.strip(), start.strip(), end.strip())
                        session.commit()
                        self.refresh_tables()
                        self.venue_allocation_done.emit()
                    finally:
                        session.close()

    def delete_timeslot(self, slot_id: int, slot_name: str):
        reply = QMessageBox.question(
            self,
            "Confirm Remove Time Slot",
            f"Are you sure you want to remove the time slot '{slot_name}'?\n\n"
            "Any students currently assigned to this time slot will have their time slot allocation reset.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            session = SessionLocal()
            try:
                ok, msg = Repository.delete_time_slot(session, slot_id)
                if ok:
                    self.refresh_tables()
                    self.venue_allocation_done.emit()
                else:
                    QMessageBox.warning(self, "Error", msg)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete time slot: {str(e)}")
            finally:
                session.close()

    def run_optimization(self):
        try:
            selected_idx = self.combo_mode.currentIndex()
            mode = "branch_wise" if selected_idx == 1 else "group_wise"

            res = VenueOptimizer.optimize_allocations(mode=mode)
            mode_name = "Branch-wise" if mode == "branch_wise" else "Group-wise"
            QMessageBox.information(
                self,
                "Venue Optimization Complete",
                f"Successfully completed {mode_name} Venue Allocation!\n\n"
                f"Assigned {res.newly_allocated_venues} students to venues and time slots."
            )
            self.refresh_tables()
            self.venue_allocation_done.emit()
        except CapacityExceededError as ce:
            QMessageBox.warning(
                self,
                "Capacity Exceeded Error",
                f"{str(ce)}\n\nPlease add more venues or time slots before running venue allocation."
            )
        except Exception as e:
            QMessageBox.critical(self, "Optimization Error", str(e))

