import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, Signal
from database.connection import SessionLocal
from database.repository import Repository

class AllocationHistoryView(QWidget):
    data_changed = Signal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Card
        header_card = QFrame()
        header_card.setProperty("class", "card-widget")
        hc_layout = QHBoxLayout(header_card)

        lbl_title = QLabel("Venue Allocation History Manager")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #F8FAFC;")
        
        btn_refresh = QPushButton("🔄 Refresh History")
        btn_refresh.setProperty("class", "secondary-btn")
        btn_refresh.clicked.connect(self.refresh_history)

        hc_layout.addWidget(lbl_title)
        hc_layout.addStretch()
        hc_layout.addWidget(btn_refresh)
        layout.addWidget(header_card)

        # Splitter for Master-Detail view
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #334155;
                width: 2px;
            }
        """)

        # Left: History Table Card
        table_card = QFrame()
        table_card.setProperty("class", "card-widget")
        tc_layout = QVBoxLayout(table_card)

        lbl_table_title = QLabel("Historical Allocation Runs")
        lbl_table_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #94A3B8;")
        tc_layout.addWidget(lbl_table_title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Timestamp", "Mode", "Students Allocated", "Venues Used"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_run_details)

        tc_layout.addWidget(self.table)
        splitter.addWidget(table_card)

        # Right: Detail Card
        detail_card = QFrame()
        detail_card.setProperty("class", "card-widget")
        dc_layout = QVBoxLayout(detail_card)

        lbl_detail_title = QLabel("Selected Run Configuration & Details")
        lbl_detail_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #94A3B8;")
        dc_layout.addWidget(lbl_detail_title)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setStyleSheet("""
            QTextEdit {
                background-color: #0F172A;
                color: #E2E8F0;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #1E293B;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        dc_layout.addWidget(self.detail_text)
        splitter.addWidget(detail_card)

        layout.addWidget(splitter)

        # Footer Action Row
        footer_layout = QHBoxLayout()
        self.btn_restore = QPushButton("Restore Selected Allocation Run")
        self.btn_restore.setProperty("class", "primary-btn")
        self.btn_restore.setStyleSheet("padding: 10px 24px; font-size: 13px; font-weight: bold;")
        self.btn_restore.clicked.connect(self.restore_selected)
        self.btn_restore.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_restore)
        layout.addLayout(footer_layout)

        self.refresh_history()

    def refresh_history(self):
        session = SessionLocal()
        try:
            runs = Repository.get_allocation_runs(session)
            self.table.setRowCount(0)
            self.detail_text.clear()
            self.btn_restore.setEnabled(False)
            
            for r in runs:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                
                # Format timestamp
                ts_str = r.allocated_at.strftime("%Y-%m-%d %H:%M:%S")
                self.table.setItem(row, 1, QTableWidgetItem(ts_str))
                
                # Format mode
                mode_str = "Group-wise" if r.mode == "group_wise" else "Branch-wise"
                self.table.setItem(row, 2, QTableWidgetItem(mode_str))
                
                self.table.setItem(row, 3, QTableWidgetItem(f"{r.student_count:,}"))
                
                # Venues list
                try:
                    venues = json.loads(r.venues_used)
                    venues_str = ", ".join(venues)
                except Exception:
                    venues_str = r.venues_used or ""
                self.table.setItem(row, 4, QTableWidgetItem(venues_str))
        except Exception as e:
            QMessageBox.critical(self, "History View Error", f"Failed to retrieve runs: {str(e)}")
        finally:
            session.close()

    def show_run_details(self):
        selected = self.table.currentRow()
        if selected < 0:
            self.detail_text.clear()
            self.btn_restore.setEnabled(False)
            return

        run_id = int(self.table.item(selected, 0).text())
        session = SessionLocal()
        try:
            from database.models import AllocationRun
            run = session.query(AllocationRun).filter(AllocationRun.id == run_id).first()
            if not run:
                self.detail_text.clear()
                self.btn_restore.setEnabled(False)
                return

            self.btn_restore.setEnabled(True)

            # Build readable details info
            details = []
            details.append(f"Allocation Run ID: {run.id}")
            details.append(f"Allocation Time: {run.allocated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            details.append(f"Allocation Mode: {'Group-wise' if run.mode == 'group_wise' else 'Branch-wise'}")
            details.append(f"Students Placed: {run.student_count:,}\n")

            # Parse config
            try:
                config_data = json.loads(run.config)
                details.append("Configuration:")
                details.append(json.dumps(config_data, indent=2))
                details.append("")
            except Exception:
                details.append(f"Configuration (Raw): {run.config}\n")

            # Parse venues
            try:
                venues_list = json.loads(run.venues_used)
                details.append(f"Venues Used ({len(venues_list)}): {', '.join(venues_list)}\n")
            except Exception:
                pass

            # Parse sample assignments
            try:
                assignments = json.loads(run.assignments_json)
                details.append(f"Total Student Assignments Saved: {len(assignments)}")
                details.append("Sample Assignments (First 20):")
                for idx, a in enumerate(assignments[:20]):
                    details.append(f" - {a['usn']}: {a['venue_name']} ({a['slot_name']})")
                if len(assignments) > 20:
                    details.append(f" ... and {len(assignments) - 20} more.")
            except Exception as e:
                details.append(f"Failed to parse assignments: {str(e)}")

            self.detail_text.setText("\n".join(details))
        except Exception as e:
            self.detail_text.setText(f"Error loading run details: {str(e)}")
        finally:
            session.close()

    def restore_selected(self):
        selected = self.table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Selection Required", "Please select an allocation run to restore.")
            return

        run_id = int(self.table.item(selected, 0).text())
        timestamp_str = self.table.item(selected, 1).text()
        mode_str = self.table.item(selected, 2).text()

        reply = QMessageBox.question(
            self,
            "Confirm Allocation Restore",
            f"ARE YOU SURE you want to restore the historical allocation run #{run_id} ({mode_str}) allocated at {timestamp_str}?\n\n"
            "This will clear current active assignments for this mode and restore assignments from the selected historical snapshot.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            session = SessionLocal()
            try:
                ok, msg = Repository.restore_allocation_run(session, run_id)
                if ok:
                    QMessageBox.information(self, "Restore Successful", msg)
                    self.data_changed.emit()
                else:
                    QMessageBox.warning(self, "Restore Failed", msg)
            except Exception as e:
                QMessageBox.critical(self, "Restore Error", f"Failed to restore run: {str(e)}")
            finally:
                session.close()
