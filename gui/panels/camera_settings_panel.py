"""Dynamic camera parameter controls with tooltips."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox,
)

from config.settings import CameraSettings


class CameraSettingsPanel(QGroupBox):
    """Editable camera parameter controls."""

    def __init__(self, settings: CameraSettings, parent=None):
        super().__init__("Camera Settings", parent)
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QFormLayout()

        self._width = QSpinBox()
        self._width.setRange(16, 1440)
        self._width.setSingleStep(2)
        self._width.setValue(self._settings.width)
        self._width.setToolTip("Camera sensor ROI width in pixels")
        layout.addRow("Width (px):", self._width)

        self._height = QSpinBox()
        self._height.setRange(16, 1080)
        self._height.setSingleStep(2)
        self._height.setValue(self._settings.height)
        self._height.setToolTip("Camera sensor ROI height in pixels")
        layout.addRow("Height (px):", self._height)

        self._pixel_format = QComboBox()
        self._pixel_format.addItems(["Mono8", "Mono12", "Mono12p"])
        self._pixel_format.setCurrentText(self._settings.pixel_format)
        layout.addRow("Pixel Format:", self._pixel_format)

        self._exposure = QDoubleSpinBox()
        self._exposure.setRange(10.0, 100000.0)
        self._exposure.setDecimals(1)
        self._exposure.setSuffix(" us")
        self._exposure.setValue(self._settings.exposure_time_us)
        self._exposure.setToolTip("Sensor exposure time in microseconds")
        layout.addRow("Exposure:", self._exposure)

        self._gain = QDoubleSpinBox()
        self._gain.setRange(0.0, 36.0)
        self._gain.setDecimals(1)
        self._gain.setSuffix(" dB")
        self._gain.setValue(self._settings.gain_db)
        self._gain.setToolTip("Signal amplification in dB")
        layout.addRow("Gain:", self._gain)

        self._fps = QDoubleSpinBox()
        self._fps.setRange(1.0, 750.0)
        self._fps.setDecimals(1)
        self._fps.setSuffix(" fps")
        self._fps.setValue(self._settings.target_frame_rate)
        self._fps.setToolTip("Target camera acquisition speed in fps")
        layout.addRow("Frame Rate:", self._fps)

        self.setLayout(layout)

    def apply_to_settings(self, settings: CameraSettings) -> CameraSettings:
        """Read widget values into a new CameraSettings."""
        return CameraSettings(
            model_name=settings.model_name,
            expected_serial=settings.expected_serial,
            width=self._width.value(),
            height=self._height.value(),
            pixel_format=self._pixel_format.currentText(),
            exposure_time_us=self._exposure.value(),
            gain_db=self._gain.value(),
            target_frame_rate=self._fps.value(),
            playback_fps=self._fps.value(),
        )
