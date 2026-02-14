"""Camera setup dialog with live preview and settings."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QMessageBox, QSplitter, QSizePolicy,
)

from config.settings import ExperimentConfig, CameraSettings
from hardware.camera_base import CameraBackend
from hardware.camera_factory import create_camera
from gui.panels.camera_preview_panel import CameraPreviewPanel
from gui.panels.camera_settings_panel import CameraSettingsPanel

logger = logging.getLogger(__name__)


class CameraSetupDialog(QDialog):
    """Wizard step 3: camera connection, preview, and settings.

    Supports window resizing and fullscreen for detailed camera inspection.
    """

    def __init__(
        self,
        config: ExperimentConfig,
        dev_mode: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Camera Setup")
        self.setMinimumSize(600, 500)
        # Allow resize and maximize
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._config = config
        self._dev_mode = dev_mode
        self._camera: Optional[CameraBackend] = None
        self._connected = False
        self._build_ui()
        self._auto_connect()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Status
        self._status_label = QLabel("Camera not connected")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        # Splitter: preview (top, resizable) | settings (bottom)
        splitter = QSplitter(Qt.Vertical)

        # Top: preview — expandable
        self._preview = CameraPreviewPanel()
        self._preview.setMinimumHeight(200)
        splitter.addWidget(self._preview)

        # Bottom: settings
        self._settings_panel = CameraSettingsPanel(self._config.camera)
        splitter.addWidget(self._settings_panel)

        # Give more space to preview by default
        splitter.setSizes([400, 200])
        splitter.setStretchFactor(0, 3)  # Preview gets 3x stretch
        splitter.setStretchFactor(1, 1)  # Settings gets 1x stretch

        layout.addWidget(splitter, stretch=1)

        # Enable/disable FPS control in dev mode
        if self._dev_mode:
            self._settings_panel._fps.setEnabled(False)
            self._settings_panel._fps.setToolTip("Frame rate not applicable in dev mode")

        # Buttons
        btn_layout = QHBoxLayout()

        reconnect_btn = QPushButton("Reconnect")
        reconnect_btn.clicked.connect(self._reconnect)
        btn_layout.addWidget(reconnect_btn)

        btn_layout.addStretch()

        confirm_btn = QPushButton("Confirm")
        confirm_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _auto_connect(self) -> None:
        """Attempt camera connection on dialog open."""
        try:
            self._camera = create_camera(self._dev_mode)
            self._camera.connect(self._config.camera)
            self._connected = True
            info = self._camera.get_device_info()
            model = info.get("model", "Unknown")
            self._status_label.setText(
                f'<span style="color:green;">Connected: {model}</span>'
            )
            self._preview.set_camera(self._camera)
            self._preview.start_preview()
        except Exception as e:
            self._status_label.setText(
                f'<span style="color:red;">Connection failed: {e}</span>'
            )
            logger.warning("Camera auto-connect failed: %s", e)

    def _reconnect(self) -> None:
        """Disconnect and reconnect with current settings."""
        self._preview.stop_preview()
        if self._camera:
            self._camera.disconnect()
        self._config.camera = self._settings_panel.apply_to_settings(self._config.camera)
        self._auto_connect()

    def _on_confirm(self) -> None:
        if not self._connected:
            result = QMessageBox.question(
                self, "No Camera",
                "Camera is not connected. Continue anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                return
        self._config.camera = self._settings_panel.apply_to_settings(self._config.camera)
        self.accept()

    @property
    def camera(self) -> Optional[CameraBackend]:
        return self._camera

    def closeEvent(self, event) -> None:
        self._preview.stop_preview()
        super().closeEvent(event)

    def reject(self) -> None:
        self._preview.stop_preview()
        if self._camera:
            self._camera.disconnect()
        super().reject()
