"""Main application window with wizard launch flow and operator layout."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QMessageBox, QApplication,
)

from config.settings import ExperimentConfig
from core.enums import ExperimentState, TrialPhase
from core.experiment_engine import ExperimentEngine
from hardware.camera_factory import create_camera
from hardware.camera_base import CameraBackend
from data.app_memory import AppMemory

from gui.panels.camera_preview_panel import CameraPreviewPanel
from gui.panels.queue_panel import QueuePanel
from gui.panels.progress_panel import ProgressPanel
from gui.panels.control_panel import ControlPanel
from gui.panels.stimulus_mirror_panel import StimulusMirrorPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level experiment GUI window.

    On launch, runs a sequential wizard (mode -> settings -> camera ->
    display/audio -> subjects). After the wizard completes, shows the
    operator-only main window.

    Stop (abort) shuts down the entire application. To start a new
    session the operator simply runs main.py again.
    """

    def __init__(self, config: ExperimentConfig):
        super().__init__()
        self.config = config
        self.camera: Optional[CameraBackend] = None
        self.engine: Optional[ExperimentEngine] = None
        self._memory = AppMemory()
        self._dev_mode = config.dev_mode
        self._screen_index = 0
        self._subjects = []

        # End-time estimation state
        self._end_time_timer: Optional[QTimer] = None
        self._total_estimated_sec: float = 0.0
        self._per_item_sec: float = 0.0
        self._experiment_started = False
        self._last_queue_index = 0
        self._expected_end: Optional[datetime] = None
        # Track dead time (operator confirm waits + pause/resume gaps)
        self._dead_time_start: Optional[datetime] = None

        self.setWindowTitle("LSCI Visual Mental Imagery Experiment")
        self.setMinimumSize(1100, 650)

        self._build_operator_ui()
        self._connect_signals()

    def show(self) -> None:
        """Override show to run wizard first."""
        super().show()
        QTimer.singleShot(100, self._run_wizard)

    def _run_wizard(self) -> None:
        """Run the multi-step wizard dialogs sequentially."""
        # Step 1: Mode selection
        from gui.dialogs.mode_selector_dialog import ModeSelectorDialog
        mode_dlg = ModeSelectorDialog(self)
        if mode_dlg.exec_() != ModeSelectorDialog.Accepted:
            self.close()
            return
        self._dev_mode = mode_dlg.dev_mode
        self.config.dev_mode = self._dev_mode

        # Step 2: Subjects
        from gui.dialogs.subject_dialog import SubjectDialog
        subject_dlg = SubjectDialog(self._memory, self)
        if subject_dlg.exec_() != SubjectDialog.Accepted:
            self.close()
            return
        self._subjects = subject_dlg.get_subjects()

        # Step 3: Experiment settings
        from gui.dialogs.experiment_settings_dialog import ExperimentSettingsDialog
        settings_dlg = ExperimentSettingsDialog(
            self.config, self._memory, self,
            n_subjects=len(self._subjects),
        )
        if settings_dlg.exec_() != ExperimentSettingsDialog.Accepted:
            self.close()
            return

        # Step 4: Camera setup
        from gui.dialogs.camera_setup_dialog import CameraSetupDialog
        camera_dlg = CameraSetupDialog(self.config, self._dev_mode, self._memory, self)
        if camera_dlg.exec_() != CameraSetupDialog.Accepted:
            self.close()
            return
        self.camera = camera_dlg.camera

        # Step 5: Display + Audio
        from gui.dialogs.display_audio_dialog import DisplayAudioDialog
        display_dlg = DisplayAudioDialog(self._memory, self)
        if display_dlg.exec_() != DisplayAudioDialog.Accepted:
            if self.camera:
                self.camera.disconnect()
            self.close()
            return
        self._screen_index = display_dlg.selected_screen

        # Configure audio device
        audio_device = display_dlg.selected_audio_device
        if audio_device:
            from audio import configure_audio
            configure_audio(audio_device)

        # Wizard complete — set up operator window
        self._setup_camera_preview()
        self.setWindowTitle(
            f"LSCI Experiment — {'Dev Mode' if self._dev_mode else 'Lab Mode'}"
        )

    def _build_operator_ui(self) -> None:
        """Build the operator window layout (shown after wizard)."""
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Horizontal)

        # Left: queue panel (includes end-time display)
        self.queue_panel = QueuePanel()
        self.queue_panel.setMinimumWidth(250)
        splitter.addWidget(self.queue_panel)

        # Center column
        center = QWidget()
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(4, 4, 4, 4)

        self.control_panel = ControlPanel()
        center_layout.addWidget(self.control_panel)

        self.progress_panel = ProgressPanel()
        center_layout.addWidget(self.progress_panel)

        self.stimulus_mirror = StimulusMirrorPanel()
        center_layout.addWidget(self.stimulus_mirror, stretch=1)

        center.setLayout(center_layout)
        splitter.addWidget(center)

        # Right column: camera preview
        self.camera_preview = CameraPreviewPanel()
        self.camera_preview.setMinimumWidth(200)
        splitter.addWidget(self.camera_preview)

        splitter.setSizes([250, 500, 300])

        main_layout = QHBoxLayout()
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)

    def _connect_signals(self) -> None:
        cp = self.control_panel
        cp.start_clicked.connect(self._on_start)
        cp.pause_clicked.connect(self._on_pause)
        cp.resume_clicked.connect(self._on_resume)
        cp.confirm_clicked.connect(self._on_confirm)
        cp.stop_clicked.connect(self._on_stop)
        cp.adjust_camera_clicked.connect(self._on_adjust_camera)

    def _setup_camera_preview(self) -> None:
        """Initialize camera preview after wizard."""
        if self.camera and self.camera.is_connected():
            self.camera_preview.set_camera(self.camera)
            self.camera_preview.start_preview()

    # --- Duration estimation ---

    def _estimate_per_trial_sec(self) -> float:
        """Estimate duration of a single shape trial in seconds.

        Precise breakdown matching trial_protocol.py flip-by-flip execution:
          Training per rep: shape + end_beep + blank + 1 stop flip
          Instruction: 5s wait + 2s wait (MP3s play async during waits)
          Measurement per cycle: imagination_dur + end_beep_dur + 2 stop flips
            + inter_delay between cycles (not after last)
            + camera start/stop overhead
          Post: 5s sleep (MP3 plays async during sleep)
        """
        t = self.config.timing
        a = self.config.audio

        # Assume 60 Hz display for stop-flip overhead (PsychoPy not running yet)
        frame_dur = 1.0 / 60.0

        # Training: shape + end_beep + blank + 1 stop flip per rep
        # (start_beep plays simultaneously with shape, no extra time)
        # The stop-end-beep flip adds 1 frame per rep
        training = t.training_repetitions * (
            t.training_shape_duration
            + a.end_imagine_duration
            + t.training_blank_duration
            + frame_dur
        )

        # Instruction sequence: MP3s play async during frame-counted waits
        instruction = 5.0 + 2.0

        # Measurement per cycle: imagination_dur + end_beep_dur + 2 stop flips
        # Stop flips: stop-start-beep (1 frame) + stop-end-beep (1 frame)
        # Camera overhead: start_recording thread init + stop_recording thread join
        camera_overhead_per_cycle = 0.05  # ~50ms for thread join + writer flush
        measurement = (
            t.imagination_cycles * (
                t.imagination_duration
                + a.end_imagine_duration
                + 2 * frame_dur
                + camera_overhead_per_cycle
            )
            + max(0, t.imagination_cycles - 1) * t.inter_imagination_delay
        )

        # Post-measurement: precise_sleep(5.0), MP3 plays async during it
        post = 5.0

        return (training + t.training_to_measurement_delay
                + instruction + measurement + post)

    def _init_end_time_tracking(self) -> None:
        """Compute estimated duration and prepare the end-time clock."""
        if not self.engine or not self.engine.queue:
            return

        per_trial = self._estimate_per_trial_sec()
        q = self.engine.queue
        # Each queue item has N shapes
        if q.items:
            shapes_per_item = len(q.items[0].shapes)
        else:
            shapes_per_item = 1

        self._per_item_sec = shapes_per_item * per_trial
        self._total_estimated_sec = q.total * self._per_item_sec
        self._experiment_started = False
        self._last_queue_index = 0
        self._expected_end = None
        self._dead_time_start = None

        # Show initial estimate as "duration" note
        total_min = int(self._total_estimated_sec // 60)
        h, m = divmod(total_min, 60)
        self.queue_panel.end_time_panel.set_note(
            f"Estimated duration: {h:02d}:{m:02d}"
        )

    def _start_end_time_clock(self) -> None:
        """Start the 1-second timer that updates the end-time display.

        Sets a fixed expected_end = now + total_estimated_sec.
        This time only shifts forward when dead time is detected
        (operator confirm waits and pause/resume gaps).
        """
        self._experiment_started = True
        self._expected_end = (
            datetime.now() + timedelta(seconds=self._total_estimated_sec)
        )
        if self._end_time_timer is None:
            self._end_time_timer = QTimer(self)
            self._end_time_timer.timeout.connect(self._update_end_time_display)
        self._end_time_timer.start(1000)
        self._update_end_time_display()

    def _update_end_time_display(self) -> None:
        """Display the fixed expected end time and remaining duration."""
        if self._expected_end is None:
            return

        now = datetime.now()
        remaining = (self._expected_end - now).total_seconds()

        if remaining <= 0:
            self.queue_panel.end_time_panel.set_time(0, 0)
            self.queue_panel.end_time_panel.set_note("Should be done!")
            return

        self.queue_panel.end_time_panel.set_time(
            self._expected_end.hour, self._expected_end.minute,
        )

        # Show remaining as note
        rem_min = int(remaining // 60)
        h, m = divmod(rem_min, 60)
        self.queue_panel.end_time_panel.set_note(
            f"~{h:02d}:{m:02d} remaining"
        )

    def _stop_end_time_clock(self) -> None:
        """Stop the end-time update timer."""
        if self._end_time_timer:
            self._end_time_timer.stop()

    # --- Actions ---

    def _on_start(self) -> None:
        if not self._subjects:
            QMessageBox.warning(self, "No Subjects", "No subjects configured.")
            return

        errors = self.config.validate()
        if errors:
            QMessageBox.warning(self, "Invalid Config", "\n".join(errors))
            return

        # Create camera if not already connected
        if self.camera is None or not self.camera.is_connected():
            self.camera = create_camera(self._dev_mode)
            try:
                self.camera.connect(self.config.camera)
            except Exception as e:
                QMessageBox.critical(self, "Camera Error", str(e))
                return
            self._setup_camera_preview()

        # Setup engine
        self.engine = ExperimentEngine(self.config, self.camera)
        self.engine.setup(self._subjects, self._screen_index)

        # Load queue into queue panel
        self.queue_panel.load_queue(self.engine.queue.items)
        self.queue_panel.highlight_index(0)
        self.queue_panel.file_monitor.clear()

        # Set mirror panel shape color from config
        self.stimulus_mirror.set_shape_color(self.config.stimulus.color_hex)

        # Initialize end-time estimation
        self._init_end_time_tracking()

        # Connect engine worker signals
        worker = self.engine.start()
        worker.state_changed.connect(self._on_state_changed)
        worker.phase_changed.connect(self._on_phase_changed)
        worker.queue_advanced.connect(self._on_queue_advanced)
        worker.trial_completed.connect(self._on_trial_completed)
        worker.progress_text.connect(self._on_progress_text)
        worker.error_occurred.connect(self._on_error)
        worker.session_finished.connect(self._on_session_finished)
        worker.stimulus_update.connect(self._on_stimulus_update)
        worker.beep_progress.connect(self._on_beep_progress)
        worker.recording_started.connect(self._on_recording_started)
        worker.recording_saved.connect(self._on_recording_saved)
        worker.recording_discarded.connect(self._on_recording_discarded)

        self.control_panel.set_preparing()
        self.progress_panel.set_status("Please wait.. preparing the experiment...")
        self.progress_panel.set_phase_text("Initializing")

    def _on_pause(self) -> None:
        if self.engine:
            self.engine.pause()

    def _on_resume(self) -> None:
        if self.engine:
            self.engine.resume()

    def _on_confirm(self) -> None:
        if self.engine:
            self.engine.confirm_next()

    def _on_stop(self) -> None:
        if not self.engine:
            return
        reply = QMessageBox.warning(
            self,
            "Stop Session",
            "This will stop the session and close the program.\n\n"
            "If you only want to re-record the current turn, "
            "press Cancel and use Pause instead.\n\n"
            "To start a new session, run the program again.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply == QMessageBox.Ok:
            self.engine.request_abort()

    def _on_adjust_camera(self) -> None:
        """Open camera settings dialog during WAITING_CONFIRM state."""
        if not self.camera:
            return

        # Pause the live preview so camera_setup_dialog can use it
        self.camera_preview.stop_preview()

        from gui.dialogs.camera_setup_dialog import CameraSetupDialog
        dlg = CameraSetupDialog(
            self.config, self._dev_mode, self._memory, self,
            mid_session=True, camera=self.camera,
        )
        if dlg.exec_() == CameraSetupDialog.Accepted:
            # Log camera settings change to session dir
            self._log_camera_settings_change()

        # Stop dialog preview and restore main preview
        dlg._preview.stop_preview()
        self._setup_camera_preview()

    def _log_camera_settings_change(self) -> None:
        """Append current camera settings to camera_settings_changes.json."""
        if not self.engine or not self.engine.session_mgr:
            return
        try:
            import json
            from dataclasses import asdict
            log_path = self.engine.session_mgr.session_dir / "camera_settings_changes.json"
            entries = []
            if log_path.exists():
                with open(log_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            entries.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "settings": asdict(self.config.camera),
            })
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
            logger.info("Camera settings updated: %s", self.config.camera)
        except Exception as e:
            logger.warning("Failed to log camera settings change: %s", e)

    # --- Engine signal handlers (called on GUI thread) ---

    def _on_state_changed(self, state: ExperimentState) -> None:
        self.control_panel.update_for_state(state)
        if state == ExperimentState.WAITING_CONFIRM:
            self.progress_panel.set_status("Waiting for operator confirmation...")
            # Start tracking dead time (operator is idle)
            self._dead_time_start = datetime.now()
        elif state == ExperimentState.PAUSED:
            # Start tracking dead time (experiment paused)
            if self._dead_time_start is None:
                self._dead_time_start = datetime.now()
        elif state == ExperimentState.RUNNING:
            # Start the end-time clock on first transition to RUNNING
            if not self._experiment_started:
                # First confirm: _expected_end is set to now() + total,
                # so discard any dead time from the initial WAITING_CONFIRM
                self._dead_time_start = None
                self._start_end_time_clock()
            # End dead time: shift expected_end forward by the idle gap
            elif self._dead_time_start is not None and self._expected_end is not None:
                dead_seconds = (datetime.now() - self._dead_time_start).total_seconds()
                self._expected_end += timedelta(seconds=dead_seconds)
                self._dead_time_start = None
                self._update_end_time_display()

    def _on_phase_changed(self, phase: TrialPhase, remaining: float) -> None:
        self.progress_panel.set_phase(phase, remaining)

    def _on_queue_advanced(self, index: int) -> None:
        self.queue_panel.highlight_index(index)
        if self.engine and self.engine.queue:
            q = self.engine.queue
            self.progress_panel.set_overall_progress(index, q.total)
        self._last_queue_index = index

    def _on_trial_completed(
        self, subject: str, shape: str, rep: int, status: str,
    ) -> None:
        self.progress_panel.set_status(
            f"Trial {status}: {subject}/{shape}/rep{rep}"
        )

    def _on_progress_text(self, text: str) -> None:
        self.progress_panel.set_status(text)

    def _on_stimulus_update(self, state: str) -> None:
        self.stimulus_mirror.update_state(state)

    def _on_beep_progress(self, current: int, total: int) -> None:
        self.progress_panel.set_turn_progress(current, total)

    def _on_recording_started(self, video_path: str) -> None:
        self.queue_panel.file_monitor.add_recording(video_path)

    def _on_recording_saved(self, video_path: str) -> None:
        self.queue_panel.file_monitor.mark_saved(video_path)

    def _on_recording_discarded(self, video_path: str) -> None:
        self.queue_panel.file_monitor.mark_discarded(video_path)

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Engine Error", msg)

    def _on_session_finished(self) -> None:
        self._stop_end_time_clock()
        self.camera_preview.stop_preview()

        if self.engine and self.engine.queue and self.engine.queue.is_done:
            # Natural completion — show completion dialog, then exit
            self.queue_panel.mark_all_complete()
            self.queue_panel.end_time_panel.clear()
            from gui.dialogs.completion_dialog import CompletionDialog
            dlg = CompletionDialog(
                str(self.engine.session_mgr.session_dir), self,
            )
            dlg.exec_()

        # Shut down the entire application
        self._shutdown()

    def _shutdown(self) -> None:
        """Clean up all resources and exit the application."""
        logger.info("Shutting down application")
        self._stop_end_time_clock()
        self.camera_preview.stop_preview()
        if self.camera and self.camera.is_connected():
            self.camera.disconnect()
        self.camera = None
        self.engine = None
        QApplication.quit()

    def closeEvent(self, event) -> None:
        """Ensure cleanup on window close."""
        if self.engine and self.engine.state == ExperimentState.RUNNING:
            self.engine.request_abort()
        if self.camera and self.camera.is_connected():
            self.camera.disconnect()
        super().closeEvent(event)
