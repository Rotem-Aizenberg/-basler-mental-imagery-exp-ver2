"""Real-time recording file status monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
)


class FileMonitorPanel(QGroupBox):
    """Displays recording file status with color-coded rows.

    - Gray + white text: Currently recording
    - Dark green + white text: Saved successfully
    - Dark red + white text: Discarded (paused/aborted)
    """

    RECORDING = "recording"
    SAVED = "saved"
    DISCARDED = "discarded"

    _COLORS = {
        RECORDING: (QColor("#555555"), QColor("#FFFFFF")),
        SAVED: (QColor("#1b5e20"), QColor("#FFFFFF")),
        DISCARDED: (QColor("#b71c1c"), QColor("#FFFFFF")),
    }

    _SUFFIX = {
        RECORDING: "  \u25cf REC",
        SAVED: "  \u2713",
        DISCARDED: "  \u2717 DISCARDED",
    }

    def __init__(self, parent=None):
        super().__init__("Recording Files", parent)
        self._items: Dict[str, QListWidgetItem] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 8, 4, 4)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setMaximumHeight(150)
        layout.addWidget(self._list)

        self._count_label = QLabel("")
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._count_label)

        self.setLayout(layout)

    def add_recording(self, video_path: str) -> None:
        """Add a new file entry with 'recording' status."""
        filename = Path(video_path).name
        item = QListWidgetItem(filename + self._SUFFIX[self.RECORDING])
        bg, fg = self._COLORS[self.RECORDING]
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(fg))
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self._list.addItem(item)
        self._items[video_path] = item
        self._list.scrollToBottom()
        self._update_count()

    def mark_saved(self, video_path: str) -> None:
        """Update existing entry to 'saved' status."""
        item = self._items.get(video_path)
        if item is None:
            return
        filename = Path(video_path).name
        item.setText(filename + self._SUFFIX[self.SAVED])
        bg, fg = self._COLORS[self.SAVED]
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(fg))
        self._update_count()

    def mark_discarded(self, video_path: str) -> None:
        """Update existing entry to 'discarded' status."""
        item = self._items.get(video_path)
        if item is None:
            return
        filename = Path(video_path).name
        item.setText(filename + self._SUFFIX[self.DISCARDED])
        bg, fg = self._COLORS[self.DISCARDED]
        item.setBackground(QBrush(bg))
        item.setForeground(QBrush(fg))
        self._update_count()

    def clear(self) -> None:
        """Remove all entries."""
        self._list.clear()
        self._items.clear()
        self._count_label.setText("")

    def _update_count(self) -> None:
        saved = sum(
            1 for item in self._items.values()
            if self._SUFFIX[self.SAVED] in item.text()
        )
        discarded = sum(
            1 for item in self._items.values()
            if self._SUFFIX[self.DISCARDED] in item.text()
        )
        total = len(self._items)
        parts = [f"{saved}/{total} saved"]
        if discarded:
            parts.append(f"{discarded} discarded")
        self._count_label.setText("  |  ".join(parts))
