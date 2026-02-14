"""Mode selector dialog: Lab Mode (Basler) vs Dev Mode (Webcam)."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)


class ModeSelectorDialog(QDialog):
    """First wizard step: choose between Lab Mode and Dev Mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Mode")
        self.setMinimumWidth(500)
        self._dev_mode = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        title = QLabel("<h2>LSCI Visual Mental Imagery Experiment</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Select experiment mode:")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Mode buttons
        btn_layout = QHBoxLayout()

        lab_btn = QPushButton("Lab Mode\n(Basler Camera)")
        lab_btn.setMinimumHeight(100)
        lab_btn.setMinimumWidth(200)
        lab_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 20px;"
        )
        lab_btn.clicked.connect(self._on_lab_mode)
        btn_layout.addWidget(lab_btn)

        dev_btn = QPushButton("Dev Mode\n(Webcam)")
        dev_btn.setMinimumHeight(100)
        dev_btn.setMinimumWidth(200)
        dev_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 20px;"
        )
        dev_btn.clicked.connect(self._on_dev_mode)
        btn_layout.addWidget(dev_btn)

        layout.addLayout(btn_layout)

        # Camera detection status
        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)

        # Check for Basler camera
        self._detect_camera()

        self.setLayout(layout)

    def _detect_camera(self) -> None:
        """Check if a Basler camera is connected."""
        try:
            from hardware.camera_factory import detect_basler
            detected, detail = detect_basler()
            if detected:
                self._status_label.setText(
                    f'<span style="color:green;">Basler camera detected: {detail}</span>'
                )
            else:
                self._status_label.setText(
                    f'<span style="color:red;">No Basler camera: {detail}</span>'
                )
        except Exception as e:
            self._status_label.setText(
                f'<span style="color:orange;">Camera check failed: {e}</span>'
            )

    def _on_lab_mode(self) -> None:
        self._dev_mode = False
        self.accept()

    def _on_dev_mode(self) -> None:
        self._dev_mode = True
        self.accept()

    @property
    def dev_mode(self) -> bool:
        return self._dev_mode
