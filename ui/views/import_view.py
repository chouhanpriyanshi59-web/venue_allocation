from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QComboBox,
    QFrame, QMessageBox, QTextEdit, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from engine.data_importer import DataImporter
from engine.column_mapper import INTERNAL_FIELDS

class ImportView(QWidget):
    import_completed = Signal()

    def __init__(self):
        super().__init__()
        self.selected_file_path: Path = None
        self.column_mapping = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # File Picker Header Card
        file_card = QFrame()
        file_card.setProperty("class", "card-widget")
        fc_layout = QHBoxLayout(file_card)

        self.lbl_file_name = QLabel("No Excel file selected.")
        self.lbl_file_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #94A3B8;")

        btn_browse = QPushButton("Browse Excel / CSV File")
        btn_browse.setProperty("class", "primary-btn")
        btn_browse.clicked.connect(self.browse_file)

        fc_layout.addWidget(self.lbl_file_name)
        fc_layout.addStretch()
        fc_layout.addWidget(btn_browse)
        layout.addWidget(file_card)

        # Mapping Card
        mapping_card = QFrame()
        mapping_card.setProperty("class", "card-widget")
        mc_layout = QVBoxLayout(mapping_card)

        lbl_map_title = QLabel("Intelligent Excel Column Schema Mapping")
        lbl_map_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #F8FAFC;")

        self.map_table = QTableWidget(0, 3)
        self.map_table.setHorizontalHeaderLabels(["Excel Column Name", "Mapped Internal Field", "Required / Optional"])
        self.map_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        mc_layout.addWidget(lbl_map_title)
        mc_layout.addWidget(self.map_table)
        layout.addWidget(mapping_card)

        # Warning / Audit Console Log
        console_card = QFrame()
        console_card.setProperty("class", "card-widget")
        cc_layout = QVBoxLayout(console_card)

        lbl_log = QLabel("Validation & Deduplication Diagnostic Output")
        lbl_log.setStyleSheet("font-size: 14px; font-weight: bold; color: #94A3B8;")

        self.txt_warnings = QTextEdit()
        self.txt_warnings.setReadOnly(True)
        self.txt_warnings.setMaximumHeight(120)

        cc_layout.addWidget(lbl_log)
        cc_layout.addWidget(self.txt_warnings)
        layout.addWidget(console_card)

        # Action Commit Footer
        footer_layout = QHBoxLayout()
        self.btn_commit = QPushButton("Commit Import & Update Database")
        self.btn_commit.setProperty("class", "primary-btn")
        self.btn_commit.setEnabled(False)
        self.btn_commit.clicked.connect(self.commit_import)

        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_commit)
        layout.addLayout(footer_layout)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel / CSV File", "", "Data Files (*.xlsx *.xls *.csv)"
        )
        if file_path:
            self.selected_file_path = Path(file_path)
            self.lbl_file_name.setText(f"Selected: {self.selected_file_path.name}")
            self.inspect_file()

    def inspect_file(self):
        try:
            mapping, unmapped, missing_required, total_rows = DataImporter.inspect_file(self.selected_file_path)
            self.column_mapping = mapping

            self.map_table.setRowCount(0)

            # Build list of options for combo boxes
            options = ["(Skip Column)"] + [meta["label"] for meta in INTERNAL_FIELDS.values()]

            for raw_col, mapped_key in mapping.items():
                row = self.map_table.rowCount()
                self.map_table.insertRow(row)
                self.map_table.setItem(row, 0, QTableWidgetItem(raw_col))

                combo = QComboBox()
                combo.addItems(options)

                current_label = INTERNAL_FIELDS[mapped_key]["label"] if mapped_key in INTERNAL_FIELDS else "(Skip Column)"
                idx = combo.findText(current_label)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

                combo.currentIndexChanged.connect(self.validate_mapping)

                self.map_table.setCellWidget(row, 1, combo)

                req_str = "REQUIRED" if mapped_key in INTERNAL_FIELDS and INTERNAL_FIELDS[mapped_key]["required"] else "OPTIONAL"
                self.map_table.setItem(row, 2, QTableWidgetItem(req_str))

            self.validate_mapping()

        except Exception as e:
            QMessageBox.critical(self, "File Inspection Error", str(e))
            self.btn_commit.setEnabled(False)

    def validate_mapping(self):
        """Dynamically checks mapping dropdowns to ensure required fields (usn & full_name) are mapped."""
        selected_fields = set()
        for row in range(self.map_table.rowCount()):
            combo: QComboBox = self.map_table.cellWidget(row, 1)
            if combo:
                label = combo.currentText()
                for key, meta in INTERNAL_FIELDS.items():
                    if meta["label"] == label:
                        selected_fields.add(key)
                        break

        missing = []
        for key, meta in INTERNAL_FIELDS.items():
            if meta["required"] and key not in selected_fields:
                missing.append(meta["label"])

        if missing:
            self.txt_warnings.setText(
                f"WARNING: The following required fields are not mapped: {', '.join(missing)}. "
                f"Please select them in the 'Mapped Internal Field' dropdowns above."
            )
            self.btn_commit.setEnabled(False)
        else:
            self.txt_warnings.setText("File inspection successful. All required fields mapped. Click 'Commit Import & Update Database' to import.")
            self.btn_commit.setEnabled(True)

    def commit_import(self):
        if not self.selected_file_path:
            return

        # Reconstruct mapping from combo boxes
        final_mapping = {}
        for row in range(self.map_table.rowCount()):
            raw_header = self.map_table.item(row, 0).text()
            combo: QComboBox = self.map_table.cellWidget(row, 1)
            selected_label = combo.currentText()

            for key, meta in INTERNAL_FIELDS.items():
                if meta["label"] == selected_label:
                    final_mapping[raw_header] = key
                    break

        try:
            res = DataImporter.import_excel(self.selected_file_path, final_mapping)
            
            warn_msg = "\n".join(res["warnings"]) if res["warnings"] else "No warnings or validation errors."
            summary = (
                f"IMPORT COMPLETED SUCCESSFULLY!\n"
                f"Total Rows: {res['total_rows']}\n"
                f"New Students: {res['new_students']}\n"
                f"Existing Students Updated: {res['updated_students']}\n"
                f"Invalid Rows: {res.get('invalid_rows', 0)}\n"
                f"Unknown Departments: {res.get('unknown_departments', 0)}\n\n"
                f"Diagnostic Audit Logs:\n{warn_msg}"
            )
            self.txt_warnings.setText(summary)
            QMessageBox.information(self, "Import Successful", f"Successfully imported {res['new_students']} new student records!")
            self.import_completed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))
