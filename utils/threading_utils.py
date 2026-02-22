"""Threading utilities for the experiment engine."""

from __future__ import annotations

import threading
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from core.enums import ExperimentState, TrialPhase, Shape


class AtomicFlag:
    """Thread-safe boolean flag."""

    def __init__(self, initial: bool = False):
        self._value = initial
        self._lock = threading.Lock()

    def set(self) -> None:
        with self._lock:
            self._value = True

    def clear(self) -> None:
        with self._lock:
            self._value = False

    @property
    def is_set(self) -> bool:
        with self._lock:
            return self._value


class ExperimentWorker(QThread):
    """QThread wrapper for the experiment engine.

    Signals are used to communicate state changes back to the GUI
    thread safely. The engine's run method is called in the QThread.
    """

    # Signals emitted to GUI
    state_changed = pyqtSignal(object)          # ExperimentState
    phase_changed = pyqtSignal(object, float)   # TrialPhase, remaining_sec
    queue_advanced = pyqtSignal(int)             # new queue index
    trial_completed = pyqtSignal(str, str, int, str)  # subject, shape, rep, status
    progress_text = pyqtSignal(str)              # status message
    error_occurred = pyqtSignal(str)             # error message
    session_finished = pyqtSignal()              # all done
    stimulus_update = pyqtSignal(str)            # current stimulus state for operator mirror
    beep_progress = pyqtSignal(int, int)          # (current_beep, total_beeps) for turn progress
    recording_started = pyqtSignal(str)            # video_path when recording begins
    recording_saved = pyqtSignal(str)              # video_path when recording completes
    recording_discarded = pyqtSignal(str)          # video_path when recording is discarded

    def __init__(self, engine_run_func, parent=None):
        super().__init__(parent)
        self._run_func = engine_run_func

    def run(self):
        try:
            self._run_func()
        except Exception as e:
            self.error_occurred.emit(str(e))
