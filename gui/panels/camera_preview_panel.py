"""Live camera preview panel using QTimer polling."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from hardware.camera_base import CameraBackend


class CameraPreviewPanel(QGroupBox):
    """Displays a live feed from the camera backend via periodic polling."""

    POLL_INTERVAL_MS = 50  # ~20 fps preview

    def __init__(self, parent=None):
        super().__init__("Camera Preview", parent)
        self._camera: Optional[CameraBackend] = None

        self._label = QLabel("No camera connected")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMinimumSize(200, 200)
        self._label.setSizePolicy(
            QLabel.sizePolicy(self._label).horizontalPolicy(),
            QLabel.sizePolicy(self._label).verticalPolicy(),
        )
        self._label.setScaledContents(False)  # We scale manually for aspect ratio
        self._label.setStyleSheet("background-color: #1a1a1a; color: #888;")

        layout = QVBoxLayout()
        layout.addWidget(self._label)
        self.setLayout(layout)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)

    def set_camera(self, camera: CameraBackend) -> None:
        self._camera = camera

    def start_preview(self) -> None:
        if self._camera and self._camera.is_connected():
            self._timer.start(self.POLL_INTERVAL_MS)

    def stop_preview(self) -> None:
        self._timer.stop()
        self._label.setText("Preview stopped")

    def _poll_frame(self) -> None:
        if self._camera is None:
            return
        frame = self._camera.get_preview_frame()
        if frame is None:
            # Try a single grab for preview when not recording
            if not self._camera.is_recording():
                frame = self._camera.grab_frame()
        if frame is not None:
            self._display_frame(frame)

    def _display_frame(self, frame) -> None:
        h, w = frame.shape[:2]
        if len(frame.shape) == 2:
            # Grayscale
            qimg = QImage(frame.data, w, h, w, QImage.Format_Grayscale8)
        else:
            bytes_per_line = 3 * w
            qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)

        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self._label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
