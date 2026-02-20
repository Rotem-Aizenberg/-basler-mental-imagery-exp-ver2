"""Dynamic camera parameter controls with tooltips."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox,
    QLabel, QSlider, QHBoxLayout, QWidget,
)

from config.settings import CameraSettings


class CameraSettingsPanel(QGroupBox):
    """Editable camera parameter controls."""

    settings_changed = pyqtSignal()

    def __init__(self, settings: CameraSettings, dev_mode: bool = False, parent=None):
        super().__init__("Camera Settings", parent)
        self._settings = settings
        self._dev_mode = dev_mode
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

        # Lab-mode only controls (Basler pypylon parameters)
        # Offset X slider — values are multiples of 4, range 0..1440
        self._offset_x_slider = QSlider(Qt.Horizontal)
        self._offset_x_slider.setRange(0, 1440 // 4)  # each step = 4 pixels
        self._offset_x_slider.setValue(self._settings.offset_x // 4)
        self._offset_x_value = QLabel(str(self._settings.offset_x))
        self._offset_x_value.setMinimumWidth(40)
        self._offset_x_slider.valueChanged.connect(
            lambda v: self._offset_x_value.setText(str(v * 4))
        )
        self._offset_x_slider.sliderReleased.connect(self.settings_changed)
        ox_widget = QWidget()
        ox_layout = QHBoxLayout()
        ox_layout.setContentsMargins(0, 0, 0, 0)
        ox_layout.addWidget(self._offset_x_slider)
        ox_layout.addWidget(self._offset_x_value)
        ox_widget.setLayout(ox_layout)
        ox_widget.setToolTip(
            "ROI horizontal offset in pixels (multiples of 4, 0 = left edge)"
        )
        self._offset_x_label = QLabel("Offset X:")
        layout.addRow(self._offset_x_label, ox_widget)
        self._offset_x_widget = ox_widget

        # Offset Y slider — values are multiples of 4, range 0..1080
        self._offset_y_slider = QSlider(Qt.Horizontal)
        self._offset_y_slider.setRange(0, 1080 // 4)
        self._offset_y_slider.setValue(self._settings.offset_y // 4)
        self._offset_y_value = QLabel(str(self._settings.offset_y))
        self._offset_y_value.setMinimumWidth(40)
        self._offset_y_slider.valueChanged.connect(
            lambda v: self._offset_y_value.setText(str(v * 4))
        )
        self._offset_y_slider.sliderReleased.connect(self.settings_changed)
        oy_widget = QWidget()
        oy_layout = QHBoxLayout()
        oy_layout.setContentsMargins(0, 0, 0, 0)
        oy_layout.addWidget(self._offset_y_slider)
        oy_layout.addWidget(self._offset_y_value)
        oy_widget.setLayout(oy_layout)
        oy_widget.setToolTip(
            "ROI vertical offset in pixels (multiples of 4, 0 = top edge)"
        )
        self._offset_y_label = QLabel("Offset Y:")
        layout.addRow(self._offset_y_label, oy_widget)
        self._offset_y_widget = oy_widget

        # Gamma
        self._gamma = QDoubleSpinBox()
        self._gamma.setRange(0.0, 4.0)
        self._gamma.setDecimals(2)
        self._gamma.setSingleStep(0.1)
        self._gamma.setValue(self._settings.gamma)
        self._gamma.setToolTip(
            "Image gamma correction (1.0 = linear, no correction)"
        )
        self._gamma_label = QLabel("Gamma:")
        layout.addRow(self._gamma_label, self._gamma)

        # Hide lab-mode controls in dev mode
        if self._dev_mode:
            for widget in (
                self._offset_x_widget, self._offset_x_label,
                self._offset_y_widget, self._offset_y_label,
                self._gamma, self._gamma_label,
            ):
                widget.setVisible(False)

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
            offset_x=self._offset_x_slider.value() * 4,
            offset_y=self._offset_y_slider.value() * 4,
            gamma=self._gamma.value(),
        )
