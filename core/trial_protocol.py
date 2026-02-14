"""Single-shape trial with PsychoPy frame-accurate timing.

Timing precision strategy
-------------------------
Scientific requirement: the training beep must start at the EXACT moment
the shape appears and stop at the EXACT moment it disappears.

PsychoPy provides hardware-level synchronisation:

1. ``win.callOnFlip(sound.play)`` registers a callback that fires at the
   exact moment the back-buffer swaps to the display (vsync).  Audio
   onset is therefore locked to visual onset within ~1 ms.

2. All durations use *frame-counting* — ``for _ in range(n): win.flip()``
   — so timing is determined by the display refresh rate, not by
   sleep-based estimates.  No drift, no jitter.

3. Tone buffers are pre-generated at exactly ``n_frames * frame_duration``
   seconds, so audio and visual are inherently duration-matched.

New instruction sequence (replaces old close/open-eyes cue tones):
    1. Training phase (unchanged)
    2. play close_your_eyes.mp3 → wait 5s → play starting.mp3 → wait 2s
    3. Measurement phase (camera starts at first beep, stops at last beep offset)
    4. Post-measurement MP3 based on context (open_your_eyes / next_participant / completed)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from config.settings import TimingSettings
from core.enums import TrialPhase, Shape
from utils.timing import precise_sleep

if TYPE_CHECKING:
    from audio.audio_manager import AudioManager
    from hardware.camera_base import CameraBackend
    from data.event_logger import EventLogger
    from stimulus.stimulus_window import StimulusWindow
    from pathlib import Path

logger = logging.getLogger(__name__)


class TrialProtocol:
    """Executes a single shape trial with frame-accurate audio/visual sync.

    All timing-critical phases use PsychoPy's vsync-locked flip loop
    and ``callOnFlip`` for audio onset/offset synchronisation.
    """

    def __init__(
        self,
        timing: TimingSettings,
        audio: "AudioManager",
        camera: "CameraBackend",
        event_logger: "EventLogger",
        stim_window: "StimulusWindow",
    ):
        self._timing = timing
        self._audio = audio
        self._camera = camera
        self._events = event_logger
        self._win = stim_window
        self._abort = False

        # Pre-compute frame counts (constant for all trials)
        self._n_shape = stim_window.duration_to_frames(timing.training_shape_duration)
        self._n_blank = stim_window.duration_to_frames(timing.training_blank_duration)
        self._n_beep = stim_window.duration_to_frames(timing.measurement_beep_duration)
        self._n_silence = stim_window.duration_to_frames(timing.measurement_silence_duration)

        # Instruction wait durations (frame-counted for consistency)
        self._n_close_eyes_wait = stim_window.duration_to_frames(5.0)
        self._n_starting_wait = stim_window.duration_to_frames(2.0)

        logger.info(
            "Frame counts — shape:%d blank:%d beep:%d silence:%d "
            "close_wait:%d start_wait:%d",
            self._n_shape, self._n_blank, self._n_beep,
            self._n_silence, self._n_close_eyes_wait, self._n_starting_wait,
        )

    def request_abort(self) -> None:
        self._abort = True

    def run(
        self,
        shape: Shape,
        subject: str,
        rep: int,
        video_path: "Path",
        is_last_shape: bool = False,
        is_last_queue_item: bool = False,
        on_phase_change: Callable = None,
        on_stimulus_update: Callable = None,
        on_beep_progress: Callable = None,
    ) -> bool:
        """Execute one complete trial for a single shape.

        Args:
            shape: Which shape to display.
            subject: Subject name.
            rep: Repetition number.
            video_path: Where to save the measurement video.
            is_last_shape: True if this is the last shape for this subject's turn.
            is_last_queue_item: True if this is the very last item in the session.
            on_phase_change: Callback(TrialPhase, remaining_sec).
            on_stimulus_update: Callback(str) for operator mirror.
            on_beep_progress: Callback(current_beep, total_beeps) for turn progress.

        Returns True if completed normally, False if aborted.
        """
        t = self._timing
        self._abort = False

        # Total beeps in this trial (training + measurement) for progress tracking
        total_beeps = t.training_repetitions + t.measurement_repetitions
        beep_counter = 0

        def _phase(phase: TrialPhase, remaining: float = 0.0):
            if on_phase_change:
                on_phase_change(phase, remaining)

        def _stim(state: str):
            if on_stimulus_update:
                on_stimulus_update(state)

        def _beep():
            nonlocal beep_counter
            beep_counter += 1
            if on_beep_progress:
                on_beep_progress(beep_counter, total_beeps)

        self._events.log("TRIAL_START", subject, shape.value, str(rep))

        # ===== Training phase =====
        for i in range(t.training_repetitions):
            if self._abort:
                return False

            _phase(TrialPhase.TRAINING_SHAPE, t.training_shape_duration)
            _stim(f"shape:{shape.value}")

            # --- Frame 1: shape appears + audio starts at vsync ---
            self._win.draw_shape(shape.value)
            self._win.call_on_flip(self._audio.play, "training")
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_SHAPE_ON", subject, shape.value, str(rep),
                f"flash_{i+1}",
            )
            self._win.flip()
            _beep()

            # --- Sustain shape for remaining frames ---
            for _ in range(self._n_shape - 1):
                if self._abort:
                    self._audio.stop("training")
                    return False
                self._win.draw_shape(shape.value)
                self._win.flip()

            # --- Clear frame: shape disappears + audio stops at vsync ---
            self._win.call_on_flip(self._audio.stop, "training")
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_SHAPE_OFF", subject, shape.value, str(rep),
                f"flash_{i+1}",
            )
            self._win.flip()  # Black frame
            _stim("blank")

            # --- Blank gap (silence, black screen) ---
            _phase(TrialPhase.TRAINING_BLANK, t.training_blank_duration)
            for _ in range(self._n_blank - 1):
                if self._abort:
                    return False
                self._win.flip()

        # ===== Instruction sequence: close your eyes =====
        if self._abort:
            return False

        _phase(TrialPhase.INSTRUCTION_CLOSE_EYES, 5.0)
        _stim("instruction:close_eyes")
        self._audio.play_instruction("close_your_eyes")
        self._events.log("INSTRUCTION_CLOSE_EYES", subject, shape.value, str(rep))

        # Wait 5 seconds (frame-counted)
        _phase(TrialPhase.INSTRUCTION_WAIT, 5.0)
        for _ in range(self._n_close_eyes_wait):
            if self._abort:
                return False
            self._win.flip()

        # Play "starting" instruction
        _phase(TrialPhase.INSTRUCTION_STARTING, 2.0)
        _stim("instruction:starting")
        self._audio.play_instruction("starting")
        self._events.log("INSTRUCTION_STARTING", subject, shape.value, str(rep))

        # Wait 2 seconds
        _phase(TrialPhase.INSTRUCTION_READY, 2.0)
        for _ in range(self._n_starting_wait):
            if self._abort:
                return False
            self._win.flip()

        # ===== Measurement phase (camera records from first beep to last beep offset) =====
        if self._abort:
            return False

        _stim("recording")

        fps = (
            self._camera._settings.target_frame_rate
            if hasattr(self._camera, "_settings") and self._camera._settings
            else 500.0
        )

        # Start recording right before first beep
        self._camera.start_recording(video_path, fps)
        self._events.log(
            "RECORDING_START", subject, shape.value, str(rep),
            str(video_path),
        )

        for i in range(t.measurement_repetitions):
            if self._abort:
                self._camera.stop_recording()
                return False

            # --- Beep start at vsync (screen stays black) ---
            _phase(TrialPhase.MEASUREMENT_BEEP, t.measurement_beep_duration)
            self._win.call_on_flip(self._audio.play, "measurement")
            self._win.call_on_flip(
                self._events.log,
                "MEASUREMENT_BEEP", subject, shape.value, str(rep),
                f"beep_{i+1}",
            )
            self._win.flip()
            _beep()

            # --- Sustain beep for remaining frames ---
            for _ in range(self._n_beep - 1):
                if self._abort:
                    self._audio.stop("measurement")
                    self._camera.stop_recording()
                    return False
                self._win.flip()

            # --- Beep stop at vsync ---
            self._win.call_on_flip(self._audio.stop, "measurement")
            self._win.flip()

            # --- Silence after every beep (including the last one,
            #     so recording continues for measurement_silence_duration) ---
            _phase(TrialPhase.MEASUREMENT_SILENCE, t.measurement_silence_duration)
            for _ in range(self._n_silence - 1):
                if self._abort:
                    self._camera.stop_recording()
                    return False
                self._win.flip()

        # Stop recording after last silence
        frames = self._camera.stop_recording()
        self._events.log(
            "RECORDING_STOP", subject, shape.value, str(rep),
            f"frames={frames}",
        )

        # ===== Post-measurement instruction =====
        # Use "experiment_completed" ONLY if this is truly the last item
        # in the entire session queue. Otherwise use "next_participant_please"
        # (even between reps of the same participant) or "open_your_eyes"
        # (between shapes within a turn).
        _phase(TrialPhase.INSTRUCTION_POST, 5.0)

        if not is_last_shape:
            # More shapes remain for this subject's turn
            _stim("instruction:open_your_eyes")
            self._audio.play_instruction("open_your_eyes")
            self._events.log("INSTRUCTION_OPEN_EYES", subject, shape.value, str(rep))
            # Wait 5 seconds before next shape training begins
            precise_sleep(5.0)
        elif is_last_queue_item:
            # Truly the last shape of the last queue item — session complete
            _stim("instruction:experiment_completed")
            self._audio.play_instruction("experiment_completed")
            self._events.log("INSTRUCTION_COMPLETED", subject, shape.value, str(rep))
            # Wait for the full MP3 to finish (+ 1s buffer) so it doesn't
            # get cut off when PsychoPy closes
            mp3_dur = self._audio.get_instruction_duration("experiment_completed")
            precise_sleep(max(5.0, mp3_dur + 1.0))
        else:
            # Last shape of this turn, but more items remain (next participant
            # or same participant's next repetition)
            _stim("instruction:next_participant")
            self._audio.play_instruction("next_participant_please")
            self._events.log("INSTRUCTION_NEXT_PARTICIPANT", subject, shape.value, str(rep))
            precise_sleep(5.0)

        _stim("idle")
        self._events.log(
            "TRIAL_END", subject, shape.value, str(rep),
            f"frames={frames}",
        )
        return True
