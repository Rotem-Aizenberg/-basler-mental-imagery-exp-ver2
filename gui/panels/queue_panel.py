"""Scrollable interleaved queue display (left sidebar)."""

from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QListWidget, QListWidgetItem, QLabel,
)

from core.session_queue import QueueItem
from gui.panels.end_time_panel import EndTimePanel
from gui.panels.file_monitor_panel import FileMonitorPanel


class QueuePanel(QGroupBox):
    """Displays the interleaved subject x rep queue."""

    def __init__(self, parent=None):
        super().__init__("Session Queue", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        self._status_label = QLabel("No queue loaded")
        layout.addWidget(self._status_label)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self._list, stretch=1)

        self.file_monitor = FileMonitorPanel()
        layout.addWidget(self.file_monitor)

        self.end_time_panel = EndTimePanel()
        layout.addWidget(self.end_time_panel)

        self.setLayout(layout)

    def load_queue(self, items: List[QueueItem]) -> None:
        """Populate the list from queue items."""
        self._list.clear()
        for i, item in enumerate(items):
            shapes_str = ", ".join(
                s.value if hasattr(s, "value") else str(s) for s in item.shapes
            )
            text = f"[{i+1}] {item.subject} | Rep {item.rep} | {shapes_str}"
            list_item = QListWidgetItem(text)
            list_item.setFlags(list_item.flags() & ~Qt.ItemIsSelectable)
            self._list.addItem(list_item)
        self._status_label.setText(f"{len(items)} items in queue")

    def highlight_index(self, index: int) -> None:
        """Highlight the current queue item and mark completed ones."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if i < index:
                item.setBackground(Qt.darkGreen)
                item.setForeground(Qt.white)
            elif i == index:
                item.setBackground(Qt.darkCyan)
                item.setForeground(Qt.white)
            else:
                item.setBackground(Qt.transparent)
                item.setForeground(Qt.black)
        # Scroll to current
        if index < self._list.count():
            self._list.scrollToItem(self._list.item(index))

    def clear(self) -> None:
        """Remove all items from the queue display."""
        self._list.clear()
        self._status_label.setText("No queue loaded")

    def mark_all_complete(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setBackground(Qt.darkGreen)
            item.setForeground(Qt.white)
        self._status_label.setText("Session complete")
