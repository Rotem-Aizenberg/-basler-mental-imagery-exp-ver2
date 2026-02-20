"""Dynamic experiment control buttons."""

from __future__ import annotations

import math

from PyQt5.QtCore import pyqtSignal, Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QWidget,
)

from core.enums import ExperimentState


class SpinnerWidget(QWidget):
    """Windows-style spinning circle indicator with rotating dots."""

    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self._dot_count = 8
        self._angle = 0
        self._color = QColor("#1565c0")
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

    def start(self) -> None:
        self._timer.start(80)

    def stop(self) -> None:
        self._timer.stop()

    def _rotate(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 4

        for i in range(self._dot_count):
            angle_rad = math.radians(self._angle + i * (360 / self._dot_count))
            x = cx + radius * math.cos(angle_rad)
            y = cy + radius * math.sin(angle_rad)

            # Trailing dots fade out and shrink
            opacity = max(0.15, 1.0 - i * 0.12)
            dot_r = max(1.5, 3.0 - i * 0.2)

            color = QColor(self._color)
            color.setAlphaF(opacity)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x - dot_r, y - dot_r, dot_r * 2, dot_r * 2))

        painter.end()


class ControlPanel(QGroupBox):
    """Experiment control buttons with dynamic visibility."""

    start_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    resume_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    confirm_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Controls", parent)
        self._is_paused = False
        self._preparing = False  # True between Start and first WAITING_CONFIRM
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()

        self._start_btn = QPushButton("Start")
        self._start_btn.setStyleSheet(
            "font-weight: bold; padding: 10px 20px; font-size: 13px;"
        )
        self._start_btn.clicked.connect(self.start_clicked)
        btn_layout.addWidget(self._start_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setStyleSheet("padding: 10px;")
        self._pause_btn.clicked.connect(self._on_pause_toggle)
        self._pause_btn.hide()
        btn_layout.addWidget(self._pause_btn)

        self._confirm_btn = QPushButton("Confirm Next")
        self._confirm_btn.setStyleSheet(
            "background-color: #2e7d32; color: white; padding: 10px; font-weight: bold;"
        )
        self._confirm_btn.clicked.connect(self.confirm_clicked)
        self._confirm_btn.hide()
        btn_layout.addWidget(self._confirm_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setStyleSheet(
            "background-color: #c62828; color: white; padding: 10px; font-weight: bold;"
        )
        self._stop_btn.clicked.connect(self.stop_clicked)
        self._stop_btn.hide()
        btn_layout.addWidget(self._stop_btn)

        # "Please wait" container with spinner + label
        self._wait_container = QWidget()
        wait_layout = QHBoxLayout()
        wait_layout.setContentsMargins(0, 0, 0, 0)
        wait_layout.addStretch()

        self._spinner = SpinnerWidget(28, self._wait_container)
        wait_layout.addWidget(self._spinner)

        self._wait_label = QLabel("Please wait.. preparing the experiment...")
        self._wait_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._wait_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #1565c0; padding: 10px;"
        )
        wait_layout.addWidget(self._wait_label)

        wait_layout.addStretch()
        self._wait_container.setLayout(wait_layout)
        self._wait_container.hide()
        btn_layout.addWidget(self._wait_container)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_pause_toggle(self) -> None:
        if self._is_paused:
            self.resume_clicked.emit()
            self._pause_btn.setText("Pause")
            self._is_paused = False
        else:
            self.pause_clicked.emit()
            self._pause_btn.setText("Resume")
            self._is_paused = True

    def set_preparing(self) -> None:
        """Show 'Please wait' with spinner instead of buttons while engine initializes."""
        self._preparing = True
        self._start_btn.hide()
        self._pause_btn.hide()
        self._confirm_btn.hide()

        self._stop_btn.hide()
        self._wait_container.show()
        self._spinner.start()

    def update_for_state(self, state: ExperimentState) -> None:
        """Show/hide buttons based on experiment state."""
        # Hide all first
        self._start_btn.hide()
        self._pause_btn.hide()
        self._confirm_btn.hide()

        self._stop_btn.hide()
        self._wait_container.hide()
        self._spinner.stop()

        if state == ExperimentState.IDLE:
            self._start_btn.show()

        elif state == ExperimentState.RUNNING:
            if self._preparing:
                # Still initializing — keep showing "Please wait" with spinner
                self._wait_container.show()
                self._spinner.start()
                return
            self._pause_btn.show()
            self._stop_btn.show()

        elif state == ExperimentState.PAUSED:
            self._pause_btn.show()
            self._pause_btn.setText("Resume")
            self._is_paused = True
            self._stop_btn.show()

        elif state == ExperimentState.WAITING_CONFIRM:
            self._preparing = False  # Engine is ready
            self._confirm_btn.show()
            self._stop_btn.show()

        elif state in (ExperimentState.COMPLETED, ExperimentState.ABORTED, ExperimentState.ERROR):
            self._preparing = False
            pass

    def set_idle(self) -> None:
        """Reset to idle state."""
        self._is_paused = False
        self._pause_btn.setText("Pause")
        self._start_btn.setText("Start")
        self.update_for_state(ExperimentState.IDLE)
