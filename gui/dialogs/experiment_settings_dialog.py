"""Experiment settings dialog: shapes, reps, timing, stimulus, output folder."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QLabel,
    QFileDialog, QLineEdit, QToolButton, QMessageBox, QColorDialog,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QScrollArea, QWidget,
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

    def __init__(self, config: ExperimentConfig, memory: AppMemory,
                 parent=None, n_subjects: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Experiment Settings")
        self.setMinimumWidth(600)
        self._config = config
        self._memory = memory
        self._n_subjects = n_subjects
        self._shape_checks: dict[str, QCheckBox] = {}
        self._selected_color = QColor(config.stimulus.color_hex)
        self._image_paths: List[str] = list(config.stimulus.image_paths)
        self._build_ui()
        self._load_from_memory()

    def _build_ui(self) -> None:
        outer = QVBoxLayout()

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout()

        # ── Stimulus mode ──
        stim_group = QGroupBox("Stimulus Mode")
        stim_layout = QVBoxLayout()

        self._mode_group = QButtonGroup(self)
        self._radio_shapes = QRadioButton("Use shapes")
        self._radio_images = QRadioButton("Use images")
        self._mode_group.addButton(self._radio_shapes, 0)
        self._mode_group.addButton(self._radio_images, 1)
        if self._config.stimulus.use_images and self._config.stimulus.image_paths:
            self._radio_images.setChecked(True)
        else:
            self._radio_shapes.setChecked(True)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._radio_shapes)
        mode_row.addWidget(self._radio_images)
        stim_layout.addLayout(mode_row)

        # ── Shape options (visible when shapes mode selected) ──
        self._shapes_widget = QWidget()
        shapes_inner = QVBoxLayout()
        shapes_inner.setContentsMargins(0, 0, 0, 0)

        shapes_row = QHBoxLayout()
        for name in self.SHAPE_OPTIONS:
            cb = QCheckBox(name.capitalize())
            cb.setChecked(name in self._config.shapes)
            cb.setToolTip("Select which shapes will be presented during training")
            self._shape_checks[name] = cb
            shapes_row.addWidget(cb)
        shapes_inner.addLayout(shapes_row)

        # Color picker
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Shape color:"))
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(32, 24)
        self._update_color_preview()
        color_row.addWidget(self._color_preview)
        self._color_btn = QPushButton("Choose Color...")
        self._color_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_btn)
        color_row.addWidget(_tooltip_btn(
            "Pick the exact color for shape stimuli. Default: white (#FFFFFF). "
            "Adjusting this also controls brightness (darker = dimmer)."))
        color_row.addStretch()
        shapes_inner.addLayout(color_row)

        self._shapes_widget.setLayout(shapes_inner)
        stim_layout.addWidget(self._shapes_widget)

        # ── Image options (visible when images mode selected) ──
        self._images_widget = QWidget()
        images_inner = QVBoxLayout()
        images_inner.setContentsMargins(0, 0, 0, 0)

        self._image_list = QListWidget()
        self._image_list.setMaximumHeight(100)
        for path in self._image_paths:
            self._image_list.addItem(Path(path).name)
        images_inner.addWidget(self._image_list)

        img_btn_row = QHBoxLayout()
        add_img_btn = QPushButton("Add Image...")
        add_img_btn.clicked.connect(self._add_image)
        img_btn_row.addWidget(add_img_btn)
        remove_img_btn = QPushButton("Remove Selected")
        remove_img_btn.clicked.connect(self._remove_image)
        img_btn_row.addWidget(remove_img_btn)
        img_btn_row.addWidget(_tooltip_btn(
            "Add image files (PNG, JPG, BMP, GIF, TIFF) to use as stimuli "
            "instead of shapes. Each image is presented in sequence like shapes."))
        img_btn_row.addStretch()
        images_inner.addLayout(img_btn_row)

        self._images_widget.setLayout(images_inner)
        stim_layout.addWidget(self._images_widget)

        stim_group.setLayout(stim_layout)
        layout.addWidget(stim_group)

        # Toggle visibility based on mode
        self._radio_shapes.toggled.connect(self._on_stim_mode_changed)
        self._on_stim_mode_changed(self._radio_shapes.isChecked())

        # ── Repetitions and timing ──
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

        self._train_to_meas_delay = QDoubleSpinBox()
        self._train_to_meas_delay.setRange(0.0, 60.0)
        self._train_to_meas_delay.setDecimals(1)
        self._train_to_meas_delay.setSuffix(" s")
        self._train_to_meas_delay.setValue(t.training_to_measurement_delay)
        form.addRow("Training→Measurement delay:", _row_with_tooltip(
            self._train_to_meas_delay,
            "Extra delay (seconds) between the training phase and the "
            "measurement phase. 0 = no extra delay (default)."))

        layout.addLayout(form)

        # ── Imagination Settings ──
        imag_group = QGroupBox("Imagination Settings")
        imag_form = QFormLayout()

        a = self._config.audio

        self._start_beep_freq = QDoubleSpinBox()
        self._start_beep_freq.setRange(100.0, 5000.0)
        self._start_beep_freq.setDecimals(0)
        self._start_beep_freq.setSuffix(" Hz")
        self._start_beep_freq.setValue(a.start_imagine_frequency)
        imag_form.addRow("Start beep freq:", _row_with_tooltip(
            self._start_beep_freq,
            "Frequency of the 'start imagining' beep (must differ from "
            "440 Hz training tone)"))

        self._start_beep_dur = QDoubleSpinBox()
        self._start_beep_dur.setRange(0.05, 2.0)
        self._start_beep_dur.setDecimals(2)
        self._start_beep_dur.setSuffix(" s")
        self._start_beep_dur.setValue(a.start_imagine_duration)
        imag_form.addRow("Start beep duration:", _row_with_tooltip(
            self._start_beep_dur,
            "Duration of the 'start imagining' beep"))

        self._end_beep_freq = QDoubleSpinBox()
        self._end_beep_freq.setRange(100.0, 5000.0)
        self._end_beep_freq.setDecimals(0)
        self._end_beep_freq.setSuffix(" Hz")
        self._end_beep_freq.setValue(a.end_imagine_frequency)
        imag_form.addRow("End beep freq:", _row_with_tooltip(
            self._end_beep_freq,
            "Frequency of the 'end imagining' beep (must differ from "
            "start beep frequency)"))

        self._end_beep_dur = QDoubleSpinBox()
        self._end_beep_dur.setRange(0.05, 2.0)
        self._end_beep_dur.setDecimals(2)
        self._end_beep_dur.setSuffix(" s")
        self._end_beep_dur.setValue(a.end_imagine_duration)
        imag_form.addRow("End beep duration:", _row_with_tooltip(
            self._end_beep_dur,
            "Duration of the 'end imagining' beep"))

        self._imagination_dur = QDoubleSpinBox()
        self._imagination_dur.setRange(1.0, 120.0)
        self._imagination_dur.setDecimals(1)
        self._imagination_dur.setSuffix(" s")
        self._imagination_dur.setValue(t.imagination_duration)
        imag_form.addRow("Imagination duration:", _row_with_tooltip(
            self._imagination_dur,
            "Total time from start beep onset to end beep onset. "
            "Camera records for: imagination_duration − start_beep − 1s delay."))

        self._inter_delay = QDoubleSpinBox()
        self._inter_delay.setRange(0.0, 30.0)
        self._inter_delay.setDecimals(1)
        self._inter_delay.setSuffix(" s")
        self._inter_delay.setValue(t.inter_imagination_delay)
        imag_form.addRow("Inter-imagination delay:", _row_with_tooltip(
            self._inter_delay,
            "Delay between end of one imagination cycle and start of "
            "the next start beep"))

        self._imagination_cycles = QSpinBox()
        self._imagination_cycles.setRange(1, 20)
        self._imagination_cycles.setValue(t.imagination_cycles)
        imag_form.addRow("Imagination cycles:", _row_with_tooltip(
            self._imagination_cycles,
            "Number of imagination cycles per measurement phase. "
            "Each cycle produces one video recording."))

        imag_group.setLayout(imag_form)
        layout.addWidget(imag_group)

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

        content.setLayout(layout)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()

        save_btn = QPushButton("Save as Default")
        save_btn.clicked.connect(self._save_defaults)
        btn_layout.addWidget(save_btn)

        duration_btn = QPushButton("Estimated Duration")
        duration_btn.setToolTip("Calculate expected experiment duration based on current settings")
        duration_btn.clicked.connect(self._show_estimated_duration)
        btn_layout.addWidget(duration_btn)

        btn_layout.addStretch()

        next_btn = QPushButton("Next")
        next_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        next_btn.clicked.connect(self._on_next)
        btn_layout.addWidget(next_btn)

        outer.addLayout(btn_layout)
        self.setLayout(outer)

    # ── Stimulus mode helpers ──

    def _on_stim_mode_changed(self, shapes_checked: bool) -> None:
        self._shapes_widget.setVisible(shapes_checked)
        self._images_widget.setVisible(not shapes_checked)

    def _update_color_preview(self) -> None:
        self._color_preview.setStyleSheet(
            f"background-color: {self._selected_color.name()}; "
            f"border: 1px solid #666;"
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            self._selected_color, self, "Choose Shape Color"
        )
        if color.isValid():
            self._selected_color = color
            self._update_color_preview()

    def _add_image(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Stimulus Image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif)"
        )
        for p in paths:
            if p not in self._image_paths:
                self._image_paths.append(p)
                self._image_list.addItem(Path(p).name)

    def _remove_image(self) -> None:
        row = self._image_list.currentRow()
        if row >= 0:
            self._image_paths.pop(row)
            self._image_list.takeItem(row)

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
            if "training_to_measurement_delay" in timing:
                self._train_to_meas_delay.setValue(timing["training_to_measurement_delay"])
            if "imagination_duration" in timing:
                self._imagination_dur.setValue(timing["imagination_duration"])
            if "imagination_cycles" in timing:
                self._imagination_cycles.setValue(timing["imagination_cycles"])
            if "inter_imagination_delay" in timing:
                self._inter_delay.setValue(timing["inter_imagination_delay"])
            # Audio imagination settings
            audio = ls.get("audio", {})
            if "start_imagine_frequency" in audio:
                self._start_beep_freq.setValue(audio["start_imagine_frequency"])
            if "start_imagine_duration" in audio:
                self._start_beep_dur.setValue(audio["start_imagine_duration"])
            if "end_imagine_frequency" in audio:
                self._end_beep_freq.setValue(audio["end_imagine_frequency"])
            if "end_imagine_duration" in audio:
                self._end_beep_dur.setValue(audio["end_imagine_duration"])
            # Stimulus settings
            stim = ls.get("stimulus", {})
            if "color_hex" in stim:
                self._selected_color = QColor(stim["color_hex"])
                self._update_color_preview()
            if "use_images" in stim and stim["use_images"]:
                self._radio_images.setChecked(True)
            if "image_paths" in stim and stim["image_paths"]:
                self._image_paths = list(stim["image_paths"])
                self._image_list.clear()
                for p in self._image_paths:
                    self._image_list.addItem(Path(p).name)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._folder_edit.text()
        )
        if folder:
            self._folder_edit.setText(folder)

    def _show_estimated_duration(self) -> None:
        """Show a dialog with estimated experiment duration based on current settings."""
        # Read current widget values
        n_shapes = sum(1 for cb in self._shape_checks.values() if cb.isChecked())
        if self._radio_images.isChecked():
            n_shapes = max(1, self._image_list.count())
        if n_shapes == 0:
            QMessageBox.warning(self, "No Stimuli", "Select at least one shape or image.")
            return

        reps = self._reps.value()
        shape_reps = self._shape_reps.value()
        train_reps = self._train_reps.value()
        train_shape = self._train_shape_dur.value()
        train_blank = self._train_blank_dur.value()
        train_to_meas = self._train_to_meas_delay.value()
        end_beep_dur = self._end_beep_dur.value()
        imag_dur = self._imagination_dur.value()
        imag_cycles = self._imagination_cycles.value()
        inter_delay = self._inter_delay.value()

        # Per-trial duration (matches trial_protocol.py execution)
        # Training: shape (start_beep overlaid) + end_beep + blank per rep
        training_phase = train_reps * (
            train_shape + end_beep_dur + train_blank
        )
        # Instruction: MP3s play async during frame-counted waits
        instruction_seq = 5.0 + 2.0
        # Measurement: imagination_dur (start beep → end beep) + end_beep per cycle
        # + inter_delay between cycles
        measurement_phase = (
            imag_cycles * imag_dur
            + imag_cycles * end_beep_dur
            + max(0, imag_cycles - 1) * inter_delay
        )
        # Post: precise_sleep(5.0), MP3 plays async during it
        post_instruction = 5.0
        per_trial = (training_phase + train_to_meas + instruction_seq
                     + measurement_phase + post_instruction)

        shapes_per_item = n_shapes * shape_reps

        # Use actual subject count if available, otherwise ask
        if self._n_subjects > 0:
            n_subjects = self._n_subjects
        else:
            from PyQt5.QtWidgets import QInputDialog
            default_subjects = len(self._memory.subjects) if self._memory.subjects else 3
            n_subjects, ok = QInputDialog.getInt(
                self, "Number of Subjects",
                "Enter expected number of subjects:",
                default_subjects, 1, 50,
            )
            if not ok:
                return

        total_queue_items = n_subjects * reps
        total_trials = total_queue_items * shapes_per_item
        total_seconds = total_trials * per_trial

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)

        QMessageBox.information(
            self, "Estimated Duration",
            f"<h3>Estimated experiment duration: "
            f"<span style='color: #1565c0;'>{hours:02d}:{minutes:02d}</span> "
            f"(HH:MM)</h3>"
            f"<p><b>Subjects:</b> {n_subjects}<br>"
            f"<b>Repetitions:</b> {reps}<br>"
            f"<b>Shapes/images:</b> {n_shapes} × {shape_reps} reps = "
            f"{shapes_per_item} per turn<br>"
            f"<b>Queue items:</b> {total_queue_items}<br>"
            f"<b>Total trials:</b> {total_trials}<br>"
            f"<b>Per trial:</b> ~{per_trial:.0f} seconds</p>"
            f"<p><i>Note: Actual duration will be longer due to operator "
            f"confirmation delays between queue items.</i></p>",
        )

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
        config.timing.training_to_measurement_delay = self._train_to_meas_delay.value()
        config.timing.imagination_duration = self._imagination_dur.value()
        config.timing.imagination_cycles = self._imagination_cycles.value()
        config.timing.inter_imagination_delay = self._inter_delay.value()
        config.audio.start_imagine_frequency = self._start_beep_freq.value()
        config.audio.start_imagine_duration = self._start_beep_dur.value()
        config.audio.end_imagine_frequency = self._end_beep_freq.value()
        config.audio.end_imagine_duration = self._end_beep_dur.value()
        config.output_base_dir = self._folder_edit.text()

        # Stimulus settings
        config.stimulus.color_hex = self._selected_color.name().upper()
        config.stimulus.use_images = self._radio_images.isChecked()
        config.stimulus.image_paths = list(self._image_paths)
