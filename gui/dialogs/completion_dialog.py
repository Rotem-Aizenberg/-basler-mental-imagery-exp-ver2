"""Session completion dialog with Open Folder button."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)


class CompletionDialog(QDialog):
    """Shown after all sessions complete successfully."""

    def __init__(self, session_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Complete")
        self.setMinimumWidth(450)
        self._session_dir = session_dir
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        title = QLabel("<h2>All sessions completed!</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        path_label = QLabel(f"Recordings saved to:\n{self._session_dir}")
        path_label.setWordWrap(True)
        path_label.setAlignment(Qt.AlignCenter)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        # Buttons
        btn_layout = QHBoxLayout()

        open_btn = QPushButton("Open Folder")
        open_btn.setStyleSheet("padding: 8px 20px;")
        open_btn.clicked.connect(self._open_folder)
        btn_layout.addWidget(open_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _open_folder(self) -> None:
        """Open the session output folder in the system file manager."""
        path = Path(self._session_dir)
        if path.exists():
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
