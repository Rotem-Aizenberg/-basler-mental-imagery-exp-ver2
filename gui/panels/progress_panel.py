"""Dual progress bars and phase display."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QProgressBar

from core.enums import TrialPhase


class ProgressPanel(QGroupBox):
    """Shows overall and current-turn progress bars with phase label."""

    def __init__(self, parent=None):
        super().__init__("Progress", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Phase label
        self._phase_label = QLabel("Phase: Idle")
        self._phase_label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self._phase_label)

        # Overall progress bar
        layout.addWidget(QLabel("Overall progress:"))
        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(True)
        layout.addWidget(self._overall_bar)

        # Current turn progress bar
        layout.addWidget(QLabel("Current turn progress:"))
        self._turn_bar = QProgressBar()
        self._turn_bar.setRange(0, 100)
        self._turn_bar.setValue(0)
        self._turn_bar.setTextVisible(True)
        layout.addWidget(self._turn_bar)

        # Status message
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

        self.setLayout(layout)

    def set_phase_text(self, text: str) -> None:
        """Set the phase label to arbitrary text."""
        self._phase_label.setText(f"Phase: {text}")

    def set_phase(self, phase: TrialPhase, remaining: float) -> None:
        phase_names = {
            TrialPhase.TRAINING_SHAPE: "Training - Shape Display",
            TrialPhase.TRAINING_BLANK: "Training - Blank",
            TrialPhase.INSTRUCTION_CLOSE_EYES: "Instruction - Close Eyes",
            TrialPhase.INSTRUCTION_WAIT: "Instruction - Waiting",
            TrialPhase.INSTRUCTION_STARTING: "Instruction - Starting",
            TrialPhase.INSTRUCTION_READY: "Instruction - Ready",
            TrialPhase.MEASUREMENT_START_BEEP: "Measurement - Start Beep",
            TrialPhase.MEASUREMENT_RECORDING_DELAY: "Measurement - Recording Delay",
            TrialPhase.MEASUREMENT_IMAGINING: "Measurement - Imagining",
            TrialPhase.MEASUREMENT_END_BEEP: "Measurement - End Beep",
            TrialPhase.MEASUREMENT_INTER_DELAY: "Measurement - Inter-cycle Delay",
            TrialPhase.INSTRUCTION_POST: "Instruction - Post",
            TrialPhase.INTER_TRIAL: "Inter-trial Gap",
        }
        self._phase_label.setText(f"Phase: {phase_names.get(phase, str(phase))}")

    def set_overall_progress(self, current: int, total: int) -> None:
        pct = int(current / total * 100) if total > 0 else 0
        self._overall_bar.setValue(pct)
        self._overall_bar.setFormat(f"{current}/{total} ({pct}%)")

    def set_turn_progress(self, current_shape: int, total_shapes: int) -> None:
        pct = int(current_shape / total_shapes * 100) if total_shapes > 0 else 0
        self._turn_bar.setValue(pct)
        self._turn_bar.setFormat(f"{current_shape}/{total_shapes} shapes ({pct}%)")

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def reset(self) -> None:
        self._phase_label.setText("Phase: Idle")
        self._overall_bar.setValue(0)
        self._overall_bar.setFormat("0/0 (0%)")
        self._turn_bar.setValue(0)
        self._turn_bar.setFormat("0/0 shapes (0%)")
        self._status_label.setText("Ready")
