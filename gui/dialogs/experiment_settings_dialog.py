"""Experiment settings dialog: shapes, reps, timing, output folder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QLabel,
    QFileDialog, QLineEdit, QToolButton, QMessageBox,
)

from config.settings import ExperimentConfig
from data.app_memory import AppMemory


def _tooltip_btn(tooltip: str) -> QToolButton:
    """Create a small '?' button that shows an info popup on click."""
    btn = QToolButton()
    btn.setText("?")
    btn.setFixedSize(22, 22)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        "font-size: 11px; font-weight: bold; "
        "border: 1px solid #666; border-radius: 11px; "
        "background-color: #e0e0e0; color: #333;"
    )
    btn.setCursor(Qt.PointingHandCursor)
    # Show a popup dialog on click
    btn.clicked.connect(lambda checked, msg=tooltip: QMessageBox.information(
        btn.window(), "Info", msg,
    ))
    return btn


def _row_with_tooltip(widget, tooltip: str):
    """Wrap a widget with a '?' tooltip button."""
    row = QHBoxLayout()
    row.addWidget(widget, stretch=1)
    row.addWidget(_tooltip_btn(tooltip))
    return row


class ExperimentSettingsDialog(QDialog):
    """Wizard step 2: experiment settings (shapes, reps, timing, output)."""

    SHAPE_OPTIONS = ["circle", "square", "triangle", "star"]

    def __init__(self, config: ExperimentConfig, memory: AppMemory, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experiment Settings")
        self.setMinimumWidth(550)
        self._config = config
        self._memory = memory
        self._shape_checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._load_from_memory()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Shapes
        shapes_group = QGroupBox("Shapes")
        shapes_layout = QHBoxLayout()
        for name in self.SHAPE_OPTIONS:
            cb = QCheckBox(name.capitalize())
            cb.setChecked(name in self._config.shapes)
            cb.setToolTip("Select which shapes will be presented during training")
            self._shape_checks[name] = cb
            shapes_layout.addWidget(cb)
        shapes_group.setLayout(shapes_layout)
        layout.addWidget(shapes_group)

        # Repetitions and timing
        form = QFormLayout()

        self._reps = QSpinBox()
        self._reps.setRange(1, 50)
        self._reps.setValue(self._config.repetitions)
        form.addRow("Repetitions:", _row_with_tooltip(
            self._reps, "Number of complete rounds for each subject"))

        self._shape_reps = QSpinBox()
        self._shape_reps.setRange(1, 10)
        self._shape_reps.setValue(self._config.shape_reps_per_subsession)
        form.addRow("Shape reps per sub-session:", _row_with_tooltip(
            self._shape_reps,
            "How many times each shape repeats within one sub-session "
            "before moving to next participant. Default 1 = each shape once."))

        t = self._config.timing

        self._train_shape_dur = QDoubleSpinBox()
        self._train_shape_dur.setRange(0.1, 10.0)
        self._train_shape_dur.setDecimals(1)
        self._train_shape_dur.setSuffix(" s")
        self._train_shape_dur.setValue(t.training_shape_duration)
        form.addRow("Training shape:", _row_with_tooltip(
            self._train_shape_dur,
            "How long the shape is displayed with the beep"))

        self._train_blank_dur = QDoubleSpinBox()
        self._train_blank_dur.setRange(0.1, 10.0)
        self._train_blank_dur.setDecimals(1)
        self._train_blank_dur.setSuffix(" s")
        self._train_blank_dur.setValue(t.training_blank_duration)
        form.addRow("Training blank:", _row_with_tooltip(
            self._train_blank_dur,
            "Silent gap between shape flashes"))

        self._train_reps = QSpinBox()
        self._train_reps.setRange(1, 20)
        self._train_reps.setValue(t.training_repetitions)
        form.addRow("Training flashes:", _row_with_tooltip(
            self._train_reps,
            "Number of shape+beep presentations per training phase"))

        self._meas_beep_dur = QDoubleSpinBox()
        self._meas_beep_dur.setRange(0.1, 10.0)
        self._meas_beep_dur.setDecimals(1)
        self._meas_beep_dur.setSuffix(" s")
        self._meas_beep_dur.setValue(t.measurement_beep_duration)
        form.addRow("Measurement beep:", _row_with_tooltip(
            self._meas_beep_dur,
            "Duration of each beep during the measurement phase"))

        self._meas_silence_dur = QDoubleSpinBox()
        self._meas_silence_dur.setRange(0.1, 10.0)
        self._meas_silence_dur.setDecimals(1)
        self._meas_silence_dur.setSuffix(" s")
        self._meas_silence_dur.setValue(t.measurement_silence_duration)
        form.addRow("Measurement silence:", _row_with_tooltip(
            self._meas_silence_dur,
            "Silent gap between measurement beeps"))

        self._meas_reps = QSpinBox()
        self._meas_reps.setRange(1, 20)
        self._meas_reps.setValue(t.measurement_repetitions)
        form.addRow("Measurement beeps:", _row_with_tooltip(
            self._meas_reps,
            "Number of beep cycles during measurement"))

        layout.addLayout(form)

        # Output folder
        folder_group = QGroupBox("Output Folder")
        folder_layout = QHBoxLayout()
        self._folder_edit = QLineEdit(self._config.output_base_dir)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # Buttons
        btn_layout = QHBoxLayout()

        save_btn = QPushButton("Save as Default")
        save_btn.clicked.connect(self._save_defaults)
        btn_layout.addWidget(save_btn)

        btn_layout.addStretch()

        next_btn = QPushButton("Next")
        next_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        next_btn.clicked.connect(self._on_next)
        btn_layout.addWidget(next_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _load_from_memory(self) -> None:
        """Pre-populate from AppMemory if available."""
        if self._memory.last_output_folder:
            self._folder_edit.setText(self._memory.last_output_folder)
        if self._memory.last_settings:
            ls = self._memory.last_settings
            # Shapes
            if "shapes" in ls:
                for name, cb in self._shape_checks.items():
                    cb.setChecked(name in ls["shapes"])
            # Repetitions
            if "repetitions" in ls:
                self._reps.setValue(ls["repetitions"])
            if "shape_reps_per_subsession" in ls:
                self._shape_reps.setValue(ls["shape_reps_per_subsession"])
            # Timing
            timing = ls.get("timing", {})
            if "training_shape_duration" in timing:
                self._train_shape_dur.setValue(timing["training_shape_duration"])
            if "training_blank_duration" in timing:
                self._train_blank_dur.setValue(timing["training_blank_duration"])
            if "training_repetitions" in timing:
                self._train_reps.setValue(timing["training_repetitions"])
            if "measurement_beep_duration" in timing:
                self._meas_beep_dur.setValue(timing["measurement_beep_duration"])
            if "measurement_silence_duration" in timing:
                self._meas_silence_dur.setValue(timing["measurement_silence_duration"])
            if "measurement_repetitions" in timing:
                self._meas_reps.setValue(timing["measurement_repetitions"])

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._folder_edit.text()
        )
        if folder:
            self._folder_edit.setText(folder)

    def _save_defaults(self) -> None:
        self.apply_to_config(self._config)
        defaults_path = Path(__file__).resolve().parent.parent.parent / "config" / "defaults.json"
        self._config.save(defaults_path)
        self._memory.update_settings(self._config.to_dict())
        self._memory.last_output_folder = self._config.output_base_dir
        self._memory.save()
        QMessageBox.information(self, "Saved", "Defaults saved successfully.")

    def _on_next(self) -> None:
        self.apply_to_config(self._config)
        errors = self._config.validate()
        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return
        # Persist all settings for next session
        self._memory.update_settings(self._config.to_dict())
        self._memory.last_output_folder = self._config.output_base_dir
        self._memory.save()
        self.accept()

    def apply_to_config(self, config: ExperimentConfig) -> None:
        """Write widget values into the config object."""
        config.shapes = [
            name for name, cb in self._shape_checks.items() if cb.isChecked()
        ]
        config.repetitions = self._reps.value()
        config.shape_reps_per_subsession = self._shape_reps.value()
        config.timing.training_shape_duration = self._train_shape_dur.value()
        config.timing.training_blank_duration = self._train_blank_dur.value()
        config.timing.training_repetitions = self._train_reps.value()
        config.timing.measurement_beep_duration = self._meas_beep_dur.value()
        config.timing.measurement_silence_duration = self._meas_silence_dur.value()
        config.timing.measurement_repetitions = self._meas_reps.value()
        config.output_base_dir = self._folder_edit.text()
