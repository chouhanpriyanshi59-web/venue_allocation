from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QLineEdit, QDialog, QFormLayout,
    QTimeEdit, QDialogButtonBox, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTime
from database.connection import SessionLocal
from database.models import Venue, TimeSlot
from database.repository import Repository
from engine.venue_optimizer import VenueOptimizer
from services.export_service import parse_time_to_minutes, format_time_str
import re

class TimeSlotInputDialog(QDialog):
    def __init__(self, parent=None, slot_name: str = "", start_time: str = "", end_time: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Time Slot Details")
        self.setModal(True)
        self.resize(320, 220)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1E293B;
                color: #F8FAFC;
            }
            QLabel {
                color: #94A3B8;
                font-size: 13px;
                font-weight: bold;
            }
            QLineEdit {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px;
            }
            QTimeEdit {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px;
            }
            QComboBox {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background-color: #38BDF8;
                color: #0F172A;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7DD3FC;
            }
        """)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Morning Session")
        self.txt_name.setText(slot_name)
        
        # Start Time
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("h:mm")
        self.time_start.setMinimumTime(QTime(1, 0))
        self.time_start.setMaximumTime(QTime(12, 59))
        self.time_start.setTime(QTime(9, 0))
        
        self.combo_start_period = QComboBox()
        self.combo_start_period.addItems(["AM", "PM"])
        
        # End Time
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("h:mm")
        self.time_end.setMinimumTime(QTime(1, 0))
        self.time_end.setMaximumTime(QTime(12, 59))
        self.time_end.setTime(QTime(10, 0))
        
        self.combo_end_period = QComboBox()
        self.combo_end_period.addItems(["AM", "PM"])
        
        # Populate values if editing
        if start_time:
            t_str = re.sub(r'\s+', ' ', start_time.strip().upper())
            match = re.match(r'(\d+):(\d+)\s*(AM|PM)', t_str)
            if match:
                h = int(match.group(1))
                m = int(match.group(2))
                period = match.group(3)
                if h > 12:
                    h -= 12
                elif h == 0:
                    h = 12
                self.time_start.setTime(QTime(h, m))
                idx = self.combo_start_period.findText(period)
                if idx >= 0:
                    self.combo_start_period.setCurrentIndex(idx)
            else:
                match_no_min = re.match(r'(\d+)\s*(AM|PM)', t_str)
                if match_no_min:
                    h = int(match_no_min.group(1))
                    period = match_no_min.group(2)
                    if h > 12:
                        h -= 12
                    elif h == 0:
                        h = 12
                    self.time_start.setTime(QTime(h, 0))
                    idx = self.combo_start_period.findText(period)
                    if idx >= 0:
                        self.combo_start_period.setCurrentIndex(idx)

        if end_time:
            t_str = re.sub(r'\s+', ' ', end_time.strip().upper())
            match = re.match(r'(\d+):(\d+)\s*(AM|PM)', t_str)
            if match:
                h = int(match.group(1))
                m = int(match.group(2))
                period = match.group(3)
                if h > 12:
                    h -= 12
                elif h == 0:
                    h = 12
                self.time_end.setTime(QTime(h, m))
                idx = self.combo_end_period.findText(period)
                if idx >= 0:
                    self.combo_end_period.setCurrentIndex(idx)
            else:
                match_no_min = re.match(r'(\d+)\s*(AM|PM)', t_str)
                if match_no_min:
                    h = int(match_no_min.group(1))
                    period = match_no_min.group(2)
                    if h > 12:
                        h -= 12
                    elif h == 0:
                        h = 12
                    self.time_end.setTime(QTime(h, 0))
                    idx = self.combo_end_period.findText(period)
                    if idx >= 0:
                        self.combo_end_period.setCurrentIndex(idx)

        start_layout = QHBoxLayout()
        start_layout.addWidget(self.time_start)
        start_layout.addWidget(self.combo_start_period)
        
        end_layout = QHBoxLayout()
        end_layout.addWidget(self.time_end)
        end_layout.addWidget(self.combo_end_period)
        
        form_layout.addRow("Slot Name:", self.txt_name)
        form_layout.addRow("Start Time:", start_layout)
        form_layout.addRow("End Time:", end_layout)
        
        layout.addLayout(form_layout)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.handle_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_values(self):
        name = self.txt_name.text().strip()
        start_hour = self.time_start.time().hour()
        start_minute = self.time_start.time().minute()
        start_period = self.combo_start_period.currentText()
        
        end_hour = self.time_end.time().hour()
        end_minute = self.time_end.time().minute()
        end_period = self.combo_end_period.currentText()
        
        start_str = f"{start_hour}:{start_minute:02d} {start_period}"
        end_str = f"{end_hour}:{end_minute:02d} {end_period}"
        return name, start_str, end_str

    def handle_accept(self):
        name, start_str, end_str = self.get_values()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Slot Name cannot be empty.")
            return
            
        start_min = parse_time_to_minutes(start_str)
        end_min = parse_time_to_minutes(end_str)
        
        if end_min <= start_min:
            QMessageBox.warning(self, "Validation Error", "Start Time must be earlier than End Time. Overnight/reverse slots are not supported.")
            return
            
        self.accept()


class VenueAllocationView(QWidget):
    venue_allocation_done = Signal()

    def __init__(self, group_name: str):
        super().__init__()
        self.group_name = group_name
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Title
        lbl_header = QLabel(f"{self.group_name} Venue Allocation")
        lbl_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC;")
        layout.addWidget(lbl_header)

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
        self.slot_table.cellDoubleClicked.connect(self.edit_timeslot)
        sb_layout.addWidget(self.slot_table)

        lists_layout.addWidget(slot_box)
        layout.addLayout(lists_layout)

        # Execute Optimization Footer Card
        footer_card = QFrame()
        footer_card.setProperty("class", "card-widget")
        footer_layout = QHBoxLayout(footer_card)

        lbl_desc = QLabel(f"{self.group_name} mode maintains dedicated venues and independent slots.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")

        btn_run_milp = QPushButton(f"Allocate {self.group_name} Venues")
        btn_run_milp.setProperty("class", "primary-btn")
        btn_run_milp.setStyleSheet("padding: 8px 20px; font-weight: bold; font-size: 13px;")
        btn_run_milp.clicked.connect(self.run_optimization)

        footer_layout.addWidget(lbl_desc)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_run_milp)
        layout.addWidget(footer_card)

        self.refresh_tables()

    def refresh_tables(self):
        session = SessionLocal()
        try:
            # Refresh Venues
            venues = session.query(Venue).filter(Venue.group_name == self.group_name).all()
            self.venue_table.setRowCount(0)
            for v in venues:
                row = self.venue_table.rowCount()
                self.venue_table.insertRow(row)
                
                item_name = QTableWidgetItem(v.name)
                item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
                self.venue_table.setItem(row, 0, item_name)
                
                item_cap = QTableWidgetItem(str(v.capacity))
                item_cap.setFlags(item_cap.flags() & ~Qt.ItemIsEditable)
                self.venue_table.setItem(row, 1, item_cap)
                
                item_status = QTableWidgetItem("Active" if v.is_active else "Inactive")
                item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
                self.venue_table.setItem(row, 2, item_status)

                btn_del_v = QPushButton("Remove")
                btn_del_v.setProperty("class", "danger-btn")
                btn_del_v.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_del_v.clicked.connect(lambda checked=False, vid=v.id, vname=v.name: self.delete_venue(vid, vname))
                self.venue_table.setCellWidget(row, 3, btn_del_v)

            # Refresh Time Slots
            slots = session.query(TimeSlot).filter(TimeSlot.group_name == self.group_name).all()
            slots = sorted(slots, key=lambda s: (s.day_number, parse_time_to_minutes(s.start_time), s.slot_name or "", s.id))
            self.slot_table.setRowCount(0)
            for s in slots:
                row = self.slot_table.rowCount()
                self.slot_table.insertRow(row)
                
                item_name = QTableWidgetItem(s.slot_name)
                item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
                item_name.setData(Qt.UserRole, s.id)
                self.slot_table.setItem(row, 0, item_name)
                
                item_start = QTableWidgetItem(format_time_str(s.start_time))
                item_start.setFlags(item_start.flags() & ~Qt.ItemIsEditable)
                self.slot_table.setItem(row, 1, item_start)
                
                item_end = QTableWidgetItem(format_time_str(s.end_time))
                item_end.setFlags(item_end.flags() & ~Qt.ItemIsEditable)
                self.slot_table.setItem(row, 2, item_end)

                btn_del_s = QPushButton("Remove")
                btn_del_s.setProperty("class", "danger-btn")
                btn_del_s.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                btn_del_s.clicked.connect(lambda checked=False, sid=s.id, sname=s.slot_name: self.delete_timeslot(sid, sname))
                self.slot_table.setCellWidget(row, 3, btn_del_s)

            # Capacity Report
            cap_report = VenueOptimizer.check_capacity(session, target_group=self.group_name, mode="group_wise")
            if cap_report.is_sufficient:
                self.lbl_cap_status.setText(f"{self.group_name} Capacity Check Passed ✓")
                self.lbl_cap_status.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981;")
                self.lbl_cap_details.setText(
                    f"Total unassigned {self.group_name.lower()} students: {cap_report.total_students:,} | Total venue capacity available: {cap_report.total_capacity:,}."
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
                    Repository.get_or_create_venue(session, name.strip(), cap, group_name=self.group_name)
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
        session = SessionLocal()
        try:
            slot_count = session.query(TimeSlot).filter(TimeSlot.group_name == self.group_name).count()
            if slot_count >= 4:
                QMessageBox.warning(self, "Validation Error", f"Maximum of 4 time slots are allowed for {self.group_name}.")
                return
        finally:
            session.close()

        dialog = TimeSlotInputDialog(self)
        if dialog.exec() == QDialog.Accepted:
            name, start, end = dialog.get_values()
            if name:
                session = SessionLocal()
                try:
                    Repository.get_or_create_time_slot(session, name, start, end, group_name=self.group_name)
                    session.commit()
                    self.refresh_tables()
                    self.venue_allocation_done.emit()
                finally:
                    session.close()

    def edit_timeslot(self, row, column):
        item = self.slot_table.item(row, 0)
        if not item:
            return
        slot_id = item.data(Qt.UserRole)
        if slot_id is None:
            return
            
        session = SessionLocal()
        try:
            ts = session.query(TimeSlot).filter(TimeSlot.id == slot_id).first()
            if not ts:
                return
                
            dialog = TimeSlotInputDialog(self, slot_name=ts.slot_name, start_time=ts.start_time, end_time=ts.end_time)
            if dialog.exec() == QDialog.Accepted:
                name, start, end = dialog.get_values()
                if name:
                    ts.slot_name = name
                    ts.start_time = start
                    ts.end_time = end
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
        # Mandatory Warning Dialog for destructive reallocation
        reply = QMessageBox.warning(
            self,
            f"Confirm {self.group_name} Venue Reallocation",
            f"WARNING: Performing a Venue Allocation will completely clear ALL existing active venue assignments for {self.group_name} and recalculate a fresh, randomized allocation for all students in this group.\n\n"
            "This operation cannot be undone. Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            res = VenueOptimizer.optimize_allocations(target_group=self.group_name, mode="group_wise")
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
                    f"{self.group_name} Venue Allocation Complete",
                    f"Successfully completed {self.group_name} Venue Allocation!\n\n"
                    f"Assigned {res.newly_allocated_venues} students to {self.group_name} venues and time slots."
                )
            self.refresh_tables()
            self.venue_allocation_done.emit()
        except Exception as e:
            QMessageBox.critical(self, "Optimization Error", str(e))


class VenueAllocationViewA(VenueAllocationView):
    def __init__(self):
        super().__init__(group_name="Group A")


class VenueAllocationViewB(VenueAllocationView):
    def __init__(self):
        super().__init__(group_name="Group B")


