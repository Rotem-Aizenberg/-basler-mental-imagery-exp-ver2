"""Single-shape trial with PsychoPy frame-accurate timing.

Timing precision strategy
-------------------------
PsychoPy provides hardware-level synchronisation:

1. ``win.callOnFlip(sound.play)`` registers a callback that fires at the
   exact moment the back-buffer swaps to the display (vsync).  Audio
   onset is therefore locked to visual onset within ~1 ms.

2. All durations use *frame-counting* — ``for _ in range(n): win.flip()``
   — so timing is determined by the display refresh rate, not by
   sleep-based estimates.  No drift, no jitter.

3. Tone buffers are pre-generated at exactly ``n_frames * frame_duration``
   seconds, so audio and visual are inherently duration-matched.

Ver2 trial sequence per shape:
    1. Training phase: shape appears WITH start beep → shape stays →
       shape disappears WITH end beep → blank
       (repeated training_repetitions times)
    2. play close_your_eyes.mp3 → wait 5s → play starting.mp3 → wait 2s
    3. Measurement phase: per-cycle imagination with discrete start/end beeps
       and individual camera recordings per cycle
    4. Post-measurement MP3 based on context
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from config.settings import TimingSettings, AudioSettings
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
        audio_settings: AudioSettings,
        audio: "AudioManager",
        camera: "CameraBackend",
        event_logger: "EventLogger",
        stim_window: "StimulusWindow",
    ):
        self._timing = timing
        self._audio_settings = audio_settings
        self._audio = audio
        self._camera = camera
        self._events = event_logger
        self._win = stim_window
        self._abort = False

        # Pre-compute frame counts (constant for all trials)
        # Training
        self._n_shape = stim_window.duration_to_frames(timing.training_shape_duration)
        self._n_blank = stim_window.duration_to_frames(timing.training_blank_duration)

        # Start/end beep (shared between training and imagination)
        self._n_start_beep = stim_window.duration_to_frames(audio_settings.start_imagine_duration)
        self._n_end_beep = stim_window.duration_to_frames(audio_settings.end_imagine_duration)

        # Imagination cycle
        self._n_recording_delay = stim_window.duration_to_frames(timing.recording_delay)
        self._n_imagination = stim_window.duration_to_frames(timing.imagination_duration)
        self._n_inter_delay = stim_window.duration_to_frames(timing.inter_imagination_delay)

        # Actual recording frames = imagination - start_beep - recording_delay
        self._n_recording_frames = (
            self._n_imagination - self._n_start_beep - self._n_recording_delay
        )
        if self._n_recording_frames < 1:
            logger.warning(
                "Recording frames < 1 (%d). imagination_duration (%.2fs) "
                "must be > start_beep (%.2fs) + recording_delay (%.2fs).",
                self._n_recording_frames,
                timing.imagination_duration,
                audio_settings.start_imagine_duration,
                timing.recording_delay,
            )
            self._n_recording_frames = 1

        # Instruction wait durations (frame-counted for consistency)
        self._n_close_eyes_wait = stim_window.duration_to_frames(5.0)
        self._n_starting_wait = stim_window.duration_to_frames(2.0)

        # Extra delay between training and measurement phases
        delay = timing.training_to_measurement_delay
        self._n_train_to_meas_delay = stim_window.duration_to_frames(delay) if delay > 0 else 0

        logger.info(
            "Frame counts — shape:%d blank:%d start_beep:%d end_beep:%d "
            "rec_delay:%d imagination:%d recording:%d inter_delay:%d",
            self._n_shape, self._n_blank, self._n_start_beep,
            self._n_end_beep, self._n_recording_delay, self._n_imagination,
            self._n_recording_frames, self._n_inter_delay,
        )

    def request_abort(self) -> None:
        self._abort = True

    def run(
        self,
        shape,
        subject: str,
        rep: int,
        video_path_factory: Callable[[int], "Path"],
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
            video_path_factory: Callable(cycle_number) -> Path for per-cycle videos.
            is_last_shape: True if this is the last shape for this subject's turn.
            is_last_queue_item: True if this is the very last item in the session.
            on_phase_change: Callback(TrialPhase, remaining_sec).
            on_stimulus_update: Callback(str) for operator mirror.
            on_beep_progress: Callback(current_beep, total_beeps) for turn progress.

        Returns True if completed normally, False if aborted.
        """
        t = self._timing
        self._abort = False

        # Normalize shape to a string name (supports Shape enum or plain string)
        shape_name = shape.value if hasattr(shape, "value") else str(shape)

        # Total beeps: 2 per training rep (start+end) + 2 per imagination cycle
        total_beeps = (t.training_repetitions * 2) + (t.imagination_cycles * 2)
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

        self._events.log("TRIAL_START", subject, shape_name, str(rep))

        # ===== Training phase =====
        # Each rep: shape + start_beep simultaneously → shape stays →
        #           shape disappears + end_beep simultaneously → blank
        for i in range(t.training_repetitions):
            if self._abort:
                return False

            # --- Shape appears WITH start beep (simultaneous on vsync) ---
            _phase(TrialPhase.TRAINING_SHAPE, t.training_shape_duration)
            _stim(f"shape:{shape_name}")

            self._win.draw_shape(shape_name)
            self._win.call_on_flip(self._audio.play, "start_imagine")
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_START_BEEP", subject, shape_name, str(rep),
                f"flash_{i+1}",
            )
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_SHAPE_ON", subject, shape_name, str(rep),
                f"flash_{i+1}",
            )
            self._win.flip()
            _beep()

            # Shape stays visible; stop start beep at the right frame
            beep_stopped = False
            for f in range(1, self._n_shape):
                if self._abort:
                    if not beep_stopped:
                        self._audio.stop("start_imagine")
                    return False
                if f == self._n_start_beep:
                    self._win.call_on_flip(self._audio.stop, "start_imagine")
                    beep_stopped = True
                self._win.draw_shape(shape_name)
                self._win.flip()

            # Safety: stop beep if shape was shorter than beep
            if not beep_stopped:
                self._audio.stop("start_imagine")

            # --- Shape disappears WITH end beep (simultaneous on vsync) ---
            _phase(TrialPhase.TRAINING_BLANK,
                   self._audio_settings.end_imagine_duration)
            self._win.call_on_flip(self._audio.play, "end_imagine")
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_END_BEEP", subject, shape_name, str(rep),
                f"flash_{i+1}",
            )
            self._win.call_on_flip(
                self._events.log,
                "TRAINING_SHAPE_OFF", subject, shape_name, str(rep),
                f"flash_{i+1}",
            )
            self._win.flip()  # Black frame + end beep starts
            _beep()
            _stim("blank")

            for _ in range(self._n_end_beep - 1):
                if self._abort:
                    self._audio.stop("end_imagine")
                    return False
                self._win.flip()

            # Stop end beep at vsync
            self._win.call_on_flip(self._audio.stop, "end_imagine")
            self._win.flip()

            # --- Blank gap (silence, black screen) ---
            _phase(TrialPhase.TRAINING_BLANK, t.training_blank_duration)
            for _ in range(self._n_blank - 1):
                if self._abort:
                    return False
                self._win.flip()

        # ===== Optional delay between training and measurement =====
        if self._n_train_to_meas_delay > 0:
            if self._abort:
                return False
            _phase(TrialPhase.INTER_TRIAL, t.training_to_measurement_delay)
            _stim("blank")
            for _ in range(self._n_train_to_meas_delay):
                if self._abort:
                    return False
                self._win.flip()

        # ===== Instruction sequence: close your eyes =====
        if self._abort:
            return False

        _phase(TrialPhase.INSTRUCTION_CLOSE_EYES, 5.0)
        _stim("instruction:close_eyes")
        self._audio.play_instruction("close_your_eyes")
        self._events.log("INSTRUCTION_CLOSE_EYES", subject, shape_name, str(rep))

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
        self._events.log("INSTRUCTION_STARTING", subject, shape_name, str(rep))

        # Wait 2 seconds
        _phase(TrialPhase.INSTRUCTION_READY, 2.0)
        for _ in range(self._n_starting_wait):
            if self._abort:
                return False
            self._win.flip()

        # ===== Measurement phase (per-cycle imagination with recording) =====
        if self._abort:
            return False

        _stim("recording")

        fps = (
            self._camera._settings.target_frame_rate
            if hasattr(self._camera, "_settings") and self._camera._settings
            else 500.0
        )

        total_frames_recorded = 0

        for i in range(t.imagination_cycles):
            if self._abort:
                return False

            cycle_num = i + 1
            cycle_video_path = video_path_factory(cycle_num)

            # --- Play start-imagining beep ---
            _phase(
                TrialPhase.MEASUREMENT_START_BEEP,
                self._audio_settings.start_imagine_duration,
            )
            self._win.call_on_flip(self._audio.play, "start_imagine")
            self._win.call_on_flip(
                self._events.log,
                "IMAGINATION_START_BEEP", subject, shape_name, str(rep),
                f"cycle_{cycle_num}",
            )
            self._win.flip()
            _beep()

            for _ in range(self._n_start_beep - 1):
                if self._abort:
                    self._audio.stop("start_imagine")
                    return False
                self._win.flip()

            # Stop start beep at vsync
            self._win.call_on_flip(self._audio.stop, "start_imagine")
            self._win.flip()

            # --- Recording delay (silence, camera not yet recording) ---
            _phase(
                TrialPhase.MEASUREMENT_RECORDING_DELAY,
                self._timing.recording_delay,
            )
            for _ in range(self._n_recording_delay - 1):
                if self._abort:
                    return False
                self._win.flip()

            # --- Start camera recording ---
            self._camera.start_recording(cycle_video_path, fps)
            self._events.log(
                "RECORDING_START", subject, shape_name, str(rep),
                f"cycle_{cycle_num} path={cycle_video_path}",
            )

            # --- Active imagination period (camera is recording) ---
            _phase(
                TrialPhase.MEASUREMENT_IMAGINING,
                self._n_recording_frames * self._win.frame_duration,
            )
            for _ in range(self._n_recording_frames):
                if self._abort:
                    self._camera.stop_recording()
                    return False
                self._win.flip()

            # --- Stop camera before end beep ---
            frames = self._camera.stop_recording()
            total_frames_recorded += frames
            self._events.log(
                "RECORDING_STOP", subject, shape_name, str(rep),
                f"cycle_{cycle_num} frames={frames}",
            )

            # --- Play end-imagining beep ---
            _phase(
                TrialPhase.MEASUREMENT_END_BEEP,
                self._audio_settings.end_imagine_duration,
            )
            self._win.call_on_flip(self._audio.play, "end_imagine")
            self._win.call_on_flip(
                self._events.log,
                "IMAGINATION_END_BEEP", subject, shape_name, str(rep),
                f"cycle_{cycle_num}",
            )
            self._win.flip()
            _beep()

            for _ in range(self._n_end_beep - 1):
                if self._abort:
                    self._audio.stop("end_imagine")
                    return False
                self._win.flip()

            # Stop end beep at vsync
            self._win.call_on_flip(self._audio.stop, "end_imagine")
            self._win.flip()

            # --- Inter-imagination delay (skip after last cycle) ---
            if i < t.imagination_cycles - 1:
                _phase(
                    TrialPhase.MEASUREMENT_INTER_DELAY,
                    t.inter_imagination_delay,
                )
                for _ in range(self._n_inter_delay):
                    if self._abort:
                        return False
                    self._win.flip()

        # ===== Post-measurement instruction =====
        _phase(TrialPhase.INSTRUCTION_POST, 5.0)

        if not is_last_shape:
            _stim("instruction:open_your_eyes")
            self._audio.play_instruction("open_your_eyes")
            self._events.log("INSTRUCTION_OPEN_EYES", subject, shape_name, str(rep))
            precise_sleep(5.0)
        elif is_last_queue_item:
            _stim("instruction:experiment_completed")
            self._audio.play_instruction("experiment_completed")
            self._events.log("INSTRUCTION_COMPLETED", subject, shape_name, str(rep))
            mp3_dur = self._audio.get_instruction_duration("experiment_completed")
            precise_sleep(max(5.0, mp3_dur + 1.0))
        else:
            _stim("instruction:next_participant")
            self._audio.play_instruction("next_participant_please")
            self._events.log("INSTRUCTION_NEXT_PARTICIPANT", subject, shape_name, str(rep))
            precise_sleep(5.0)

        _stim("idle")
        self._events.log(
            "TRIAL_END", subject, shape_name, str(rep),
            f"total_frames={total_frames_recorded} cycles={t.imagination_cycles}",
        )
        return True
