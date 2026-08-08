from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from services.export_service import ExportService
from config import EXPORTS_DIR

class ExportView(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header Card
        lbl_title = QLabel("Enterprise Export & Reporting Center")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F8FAFC;")
        layout.addWidget(lbl_title)

        # Export Options Grid
        grid_layout = QHBoxLayout()

        # Group-wise Excel Export Card
        group_card = QFrame()
        group_card.setProperty("class", "card-widget")
        gc_layout = QVBoxLayout(group_card)

        lbl_g_title = QLabel("Group-wise Allocation Export")
        lbl_g_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38BDF8;")
        lbl_g_desc = QLabel("Generates Excel file with Group-wise Venue & Time Slot assignments.")
        lbl_g_desc.setWordWrap(True)
        lbl_g_desc.setStyleSheet("color: #94A3B8;")

        btn_exp_group = QPushButton("Export Group-wise Excel")
        btn_exp_group.setProperty("class", "primary-btn")
        btn_exp_group.clicked.connect(self.export_group_excel)

        gc_layout.addWidget(lbl_g_title)
        gc_layout.addWidget(lbl_g_desc)
        gc_layout.addStretch()
        gc_layout.addWidget(btn_exp_group)
        grid_layout.addWidget(group_card)

        # Branch-wise Excel Export Card
        branch_card = QFrame()
        branch_card.setProperty("class", "card-widget")
        bc_layout = QVBoxLayout(branch_card)

        lbl_b_title = QLabel("Branch-wise Allocation Export")
        lbl_b_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #8B5CF6;")
        lbl_b_desc = QLabel("Generates Excel file with Branch-wise (Department) Venue & Time Slot assignments.")
        lbl_b_desc.setWordWrap(True)
        lbl_b_desc.setStyleSheet("color: #94A3B8;")

        btn_exp_branch = QPushButton("Export Branch-wise Excel")
        btn_exp_branch.setProperty("class", "primary-btn")
        btn_exp_branch.setStyleSheet("background-color: #8B5CF6;")
        btn_exp_branch.clicked.connect(self.export_branch_excel)

        bc_layout.addWidget(lbl_b_title)
        bc_layout.addWidget(lbl_b_desc)
        bc_layout.addStretch()
        bc_layout.addWidget(btn_exp_branch)
        grid_layout.addWidget(branch_card)

        # Master Excel & Reports Card
        master_card = QFrame()
        master_card.setProperty("class", "card-widget")
        mc_layout = QVBoxLayout(master_card)

        lbl_m_title = QLabel("Master Report & Formats")
        lbl_m_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981;")
        lbl_m_desc = QLabel("Generates Master Excel report side-by-side or PDF Attendance sheets.")
        lbl_m_desc.setWordWrap(True)
        lbl_m_desc.setStyleSheet("color: #94A3B8;")

        btn_exp_master = QPushButton("Export Master Excel")
        btn_exp_master.setProperty("class", "secondary-btn")
        btn_exp_master.clicked.connect(self.export_master_excel)

        btn_exp_pdf = QPushButton("Generate Attendance PDF")
        btn_exp_pdf.setProperty("class", "secondary-btn")
        btn_exp_pdf.clicked.connect(self.export_pdf)

        mc_layout.addWidget(lbl_m_title)
        mc_layout.addWidget(lbl_m_desc)
        mc_layout.addStretch()
        mc_layout.addWidget(btn_exp_master)
        mc_layout.addWidget(btn_exp_pdf)
        grid_layout.addWidget(master_card)

        layout.addLayout(grid_layout)

    def export_group_excel(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Group-wise Allocation Export", str(EXPORTS_DIR / "Group-wise Allocation.xlsx"), "Excel Files (*.xlsx)"
        )
        if dest:
            try:
                out = ExportService.export_group_wise_excel(Path(dest))
                QMessageBox.information(self, "Export Complete", f"Successfully exported Group-wise Excel file to:\n{out}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def export_branch_excel(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Branch-wise Allocation Export", str(EXPORTS_DIR / "Branch-wise Allocation.xlsx"), "Excel Files (*.xlsx)"
        )
        if dest:
            try:
                out = ExportService.export_branch_wise_excel(Path(dest))
                QMessageBox.information(self, "Export Complete", f"Successfully exported Branch-wise Excel file to:\n{out}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def export_master_excel(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Master Excel Export", str(EXPORTS_DIR / "Master_Allocation_Report.xlsx"), "Excel Files (*.xlsx)"
        )
        if dest:
            try:
                out = ExportService.export_excel_master(Path(dest))
                QMessageBox.information(self, "Export Complete", f"Successfully exported Master Excel workbook to:\n{out}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def export_csv(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Flat CSV Export", str(EXPORTS_DIR / "Student_Allocations.csv"), "CSV Files (*.csv)"
        )
        if dest:
            try:
                out = ExportService.export_csv(Path(dest))
                QMessageBox.information(self, "Export Complete", f"Successfully exported CSV file to:\n{out}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def export_pdf(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Attendance Sheet PDF", str(EXPORTS_DIR / "Attendance_Sheet.pdf"), "PDF Files (*.pdf)"
        )
        if dest:
            try:
                out = ExportService.export_pdf_attendance_sheet(Path(dest))
                QMessageBox.information(self, "Export Complete", f"Successfully generated PDF attendance sheet:\n{out}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
