"""Main application window with wizard launch flow and operator layout."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
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

        self.setWindowTitle("LSCI Visual Mental Imagery Experiment")
        self.setMinimumSize(1100, 650)

        self._build_operator_ui()
        self._connect_signals()

    def show(self) -> None:
        """Override show to run wizard first."""
        super().show()
        from PyQt5.QtCore import QTimer
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

        # Step 2: Experiment settings
        from gui.dialogs.experiment_settings_dialog import ExperimentSettingsDialog
        settings_dlg = ExperimentSettingsDialog(self.config, self._memory, self)
        if settings_dlg.exec_() != ExperimentSettingsDialog.Accepted:
            self.close()
            return

        # Step 3: Camera setup
        from gui.dialogs.camera_setup_dialog import CameraSetupDialog
        camera_dlg = CameraSetupDialog(self.config, self._dev_mode, self._memory, self)
        if camera_dlg.exec_() != CameraSetupDialog.Accepted:
            self.close()
            return
        self.camera = camera_dlg.camera

        # Step 4: Display + Audio
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

        # Step 5: Subjects
        from gui.dialogs.subject_dialog import SubjectDialog
        subject_dlg = SubjectDialog(self._memory, self)
        if subject_dlg.exec_() != SubjectDialog.Accepted:
            if self.camera:
                self.camera.disconnect()
            self.close()
            return
        self._subjects = subject_dlg.get_subjects()

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

        # Left: queue panel
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
        cp.skip_clicked.connect(self._on_confirm)  # Skip = confirm (advance)
        cp.stop_clicked.connect(self._on_stop)

    def _setup_camera_preview(self) -> None:
        """Initialize camera preview after wizard."""
        if self.camera and self.camera.is_connected():
            self.camera_preview.set_camera(self.camera)
            self.camera_preview.start_preview()

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

        self.control_panel.update_for_state(ExperimentState.RUNNING)

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

    # --- Engine signal handlers (called on GUI thread) ---

    def _on_state_changed(self, state: ExperimentState) -> None:
        self.control_panel.update_for_state(state)
        if state == ExperimentState.WAITING_CONFIRM:
            self.progress_panel.set_status("Waiting for operator confirmation...")

    def _on_phase_changed(self, phase: TrialPhase, remaining: float) -> None:
        self.progress_panel.set_phase(phase, remaining)

    def _on_queue_advanced(self, index: int) -> None:
        self.queue_panel.highlight_index(index)
        if self.engine and self.engine.queue:
            q = self.engine.queue
            self.progress_panel.set_overall_progress(index, q.total)

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

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Engine Error", msg)

    def _on_session_finished(self) -> None:
        self.camera_preview.stop_preview()

        if self.engine and self.engine.queue and self.engine.queue.is_done:
            # Natural completion — show completion dialog, then exit
            self.queue_panel.mark_all_complete()
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
