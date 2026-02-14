"""Subject entry dialog with history loading."""

from __future__ import annotations

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QListWidget, QListWidgetItem,
)

from data.app_memory import AppMemory


class SubjectDialog(QDialog):
    """Wizard step 5: enter subject names, optionally load from history."""

    def __init__(self, memory: AppMemory, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Subjects")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._memory = memory
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        layout.addWidget(QLabel("<b>Enter participant names:</b>"))

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Subject")
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_row)
        history_btn = QPushButton("Load from Previous")
        history_btn.setToolTip("Load subject names from a previous session")
        history_btn.clicked.connect(self._load_from_history)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(history_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Name", "Notes"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch,
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch,
        )
        layout.addWidget(self._table)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        confirm_btn = QPushButton("Confirm")
        confirm_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        confirm_btn.clicked.connect(self._on_confirm)
        bottom_layout.addWidget(confirm_btn)

        layout.addLayout(bottom_layout)
        self.setLayout(layout)

        # Add one default row
        self._add_row()

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(f"Subject_{row + 1}"))
        self._table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_row(self) -> None:
        rows = sorted(
            set(idx.row() for idx in self._table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self._table.removeRow(row)

    def _load_from_history(self) -> None:
        """Open a multi-select dialog with previous subject names."""
        history = self._memory.get_subject_history()
        if not history:
            QMessageBox.information(
                self, "No History",
                "No previous subject names found."
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Select from Previous Subjects")
        dlg.setMinimumWidth(300)
        dlg_layout = QVBoxLayout()

        dlg_layout.addWidget(QLabel("Select subjects to add:"))

        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.MultiSelection)
        for name in history:
            list_widget.addItem(name)
        dlg_layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("Add Selected")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dlg_layout.addLayout(btn_layout)

        dlg.setLayout(dlg_layout)

        if dlg.exec_() == QDialog.Accepted:
            selected = [item.text() for item in list_widget.selectedItems()]
            for name in selected:
                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setItem(row, 0, QTableWidgetItem(name))
                self._table.setItem(row, 1, QTableWidgetItem(""))

    def _on_confirm(self) -> None:
        subjects = self.get_subjects()
        if not subjects:
            QMessageBox.warning(self, "No Subjects", "Add at least one subject.")
            return
        self.accept()

    def get_subjects(self) -> List[str]:
        """Return list of non-empty subject names."""
        names = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text().strip():
                names.append(item.text().strip())
        return names
