import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QStatusBar, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from config import APP_NAME, APP_VERSION
from database.connection import init_db
from ui.styles.theme import DARK_STYLESHEET
from ui.views.dashboard_view import DashboardView
from ui.views.import_view import ImportView
from ui.views.student_view import StudentView
from ui.views.group_view import GroupAllocationView
from ui.views.venue_view import VenueAllocationViewA, VenueAllocationViewB
from ui.views.branch_venue_view import BranchVenueAllocationView
from ui.views.backup_view import BackupRollbackView
from ui.views.history_view import AllocationHistoryView
from ui.views.export_view import ExportView
from ui.views.logs_view import LogsSettingsView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 800)

        # Initialize Database Tables
        init_db()

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("SidebarWidget")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 12, 8, 12)
        sb_layout.setSpacing(4)

        # App Brand Title
        brand_lbl = QLabel("NEXUS ALLOCATE")
        brand_lbl.setObjectName("SidebarTitle")
        sb_layout.addWidget(brand_lbl)

        # Navigation Button Group
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.views_dict = {}
        self.stacked_widget = QStackedWidget()

        nav_items = [
            ("dashboard", "📊 Dashboard", DashboardView),
            ("import", "📥 Import Excel", ImportView),
            ("students", "👥 Student Database", StudentView),
            ("group", "🔀 Group Allocation", GroupAllocationView),
            ("venue_group_a", "🏛️ Group A Venue Alloc", VenueAllocationViewA),
            ("venue_group_b", "🏛️ Group B Venue Alloc", VenueAllocationViewB),
            ("venue_branch", "🏢 Branch Venue Alloc", BranchVenueAllocationView),
            ("history", "⏳ Allocation History", AllocationHistoryView),
            ("backup", "🛡️ Backup & Rollback", BackupRollbackView),
            ("export", "📤 Export Center", ExportView),
            ("logs", "📜 Audit Logs", LogsSettingsView),
        ]

        for idx, (nav_id, label, view_cls) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)

            view_inst = view_cls()
            self.stacked_widget.addWidget(view_inst)
            self.views_dict[nav_id] = (btn, view_inst, idx)

            self.nav_group.addButton(btn, idx)
            sb_layout.addWidget(btn)

            # Signal wiring
            if hasattr(view_inst, 'request_nav'):
                view_inst.request_nav.connect(self.navigate_to)
            if hasattr(view_inst, 'data_changed'):
                view_inst.data_changed.connect(self.on_data_changed)
            if hasattr(view_inst, 'import_completed'):
                view_inst.import_completed.connect(self.on_data_changed)
            if hasattr(view_inst, 'allocation_done'):
                view_inst.allocation_done.connect(self.on_data_changed)
            if hasattr(view_inst, 'venue_allocation_done'):
                view_inst.venue_allocation_done.connect(self.on_data_changed)
            if hasattr(view_inst, 'branch_allocation_done'):
                view_inst.branch_allocation_done.connect(self.on_data_changed)
            if hasattr(view_inst, 'db_restored'):
                view_inst.db_restored.connect(self.on_data_changed)

        self.nav_group.idClicked.connect(self.on_nav_clicked)

        sb_layout.addStretch()
        
        # Sidebar Footer Status
        ver_lbl = QLabel(f"Enterprise Ed. v{APP_VERSION}")
        ver_lbl.setStyleSheet("color: #64748B; font-size: 11px; padding: 8px;")
        sb_layout.addWidget(ver_lbl)

        root_layout.addWidget(sidebar)

        # --- Right Content Workspace ---
        workspace = QWidget()
        ws_layout = QVBoxLayout(workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.setSpacing(0)

        # Header Bar
        header = QFrame()
        header.setObjectName("HeaderWidget")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 12, 16, 12)

        self.header_title = QLabel("Executive Dashboard")
        self.header_title.setObjectName("HeaderTitle")

        h_layout.addWidget(self.header_title)
        h_layout.addStretch()
        
        ws_layout.addWidget(header)
        ws_layout.addWidget(self.stacked_widget)

        root_layout.addWidget(workspace)

        # Status Bar
        self.statusBar().showMessage("System Ready | Database: SQLite (WAL Mode)")

    def on_nav_clicked(self, idx: int):
        self.stacked_widget.setCurrentIndex(idx)
        for nav_id, (btn, view_inst, view_idx) in self.views_dict.items():
            if view_idx == idx:
                raw_title = btn.text().split(" ", 1)[-1]
                self.header_title.setText(raw_title)
                if hasattr(view_inst, 'refresh_dashboard'):
                    view_inst.refresh_dashboard()
                elif hasattr(view_inst, 'load_data'):
                    view_inst.load_data()
                break

    def navigate_to(self, nav_id: str):
        if nav_id in self.views_dict:
            btn, _, idx = self.views_dict[nav_id]
            btn.setChecked(True)
            self.on_nav_clicked(idx)

    def on_data_changed(self):
        # Refresh all active views when database state updates
        for nav_id, (btn, view_inst, view_idx) in self.views_dict.items():
            if hasattr(view_inst, 'refresh_dashboard'):
                view_inst.refresh_dashboard()
            if hasattr(view_inst, 'load_data'):
                view_inst.load_data()
            if hasattr(view_inst, 'refresh_preview'):
                view_inst.refresh_preview()
            if hasattr(view_inst, 'refresh_tables'):
                view_inst.refresh_tables()
            if hasattr(view_inst, 'refresh_backups'):
                view_inst.refresh_backups()
            if hasattr(view_inst, 'refresh_logs'):
                view_inst.refresh_logs()

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
