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

Ver2 trial sequence per shape (block mode, ``run()``):
    1. Training phase: shape appears WITH start beep → shape stays →
       shape disappears WITH end beep → blank
       (repeated training_repetitions times)
    2. play close_your_eyes.mp3 → wait 5s → play starting.mp3 → wait 2s
    3. Measurement phase: per-cycle imagination with discrete start/end beeps
       and individual camera recordings per cycle
    4. Post-measurement MP3 based on context

Interleaving mode (``run_interleaved()``) runs one whole subject turn:
    1. play "Observe the screen and memorize the shapes" MP3
    2. Training phase for EVERY shape in sequence
    3. play close_your_eyes.mp3 → wait 5s
    4. For each entry of a pre-shuffled cycle sequence:
       play "Imagine a <shape>" MP3 → gap → start beep → recording →
       end beep → inter-cycle delay
    5. Post-measurement MP3 based on context
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List, Optional

from config.settings import TimingSettings, AudioSettings
from core.enums import TrialPhase
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
        self.last_completed_cycle = 0  # updated after each successful cycle

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

    # --- Shared building blocks -----------------------------------------

    def _camera_fps(self) -> float:
        return (
            self._camera._settings.target_frame_rate
            if hasattr(self._camera, "_settings") and self._camera._settings
            else 500.0
        )

    def _run_training_reps(
        self, shape_name: str, subject: str, rep: int,
        _phase: Callable, _stim: Callable, _beep: Callable,
    ) -> bool:
        """Run the full training phase for one shape.

        Each rep: shape + start_beep simultaneously → shape stays →
        shape disappears + end_beep simultaneously → blank.

        Returns False if aborted.
        """
        t = self._timing
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

        return True

    def _run_measurement_cycle(
        self,
        shape_name: str,
        subject: str,
        rep: int,
        cycle_label: str,
        video_path: "Path",
        fps: float,
        _phase: Callable,
        _beep: Callable,
        on_recording_started: Callable = None,
        on_recording_saved: Callable = None,
    ) -> Optional[int]:
        """Run one imagination cycle: start beep → delay → record → end beep.

        Returns the number of frames recorded, or None if aborted.
        """
        # --- Play start-imagining beep ---
        _phase(
            TrialPhase.MEASUREMENT_START_BEEP,
            self._audio_settings.start_imagine_duration,
        )
        self._win.call_on_flip(self._audio.play, "start_imagine")
        self._win.call_on_flip(
            self._events.log,
            "IMAGINATION_START_BEEP", subject, shape_name, str(rep),
            cycle_label,
        )
        self._win.flip()
        _beep()

        for _ in range(self._n_start_beep - 1):
            if self._abort:
                self._audio.stop("start_imagine")
                return None
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
                return None
            self._win.flip()

        # --- Start camera recording ---
        self._camera.start_recording(video_path, fps)
        if on_recording_started:
            on_recording_started(str(video_path))
        self._events.log(
            "RECORDING_START", subject, shape_name, str(rep),
            f"{cycle_label} path={video_path}",
        )

        # --- Active imagination period (camera is recording) ---
        _phase(
            TrialPhase.MEASUREMENT_IMAGINING,
            self._n_recording_frames * self._win.frame_duration,
        )
        for _ in range(self._n_recording_frames):
            if self._abort:
                self._camera.stop_recording()
                return None
            self._win.flip()

        # --- Stop camera before end beep ---
        frames = self._camera.stop_recording()
        if on_recording_saved:
            on_recording_saved(str(video_path))
        self._events.log(
            "RECORDING_STOP", subject, shape_name, str(rep),
            f"{cycle_label} frames={frames}",
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
            cycle_label,
        )
        self._win.flip()
        _beep()

        for _ in range(self._n_end_beep - 1):
            if self._abort:
                self._audio.stop("end_imagine")
                return None
            self._win.flip()

        # Stop end beep at vsync
        self._win.call_on_flip(self._audio.stop, "end_imagine")
        self._win.flip()

        return frames

    def _play_instruction_and_wait(
        self,
        name: str,
        phase: TrialPhase,
        gap_after: float,
        subject: str,
        shape_name: str,
        rep: int,
        event_type: str,
        _phase: Callable,
        _stim: Callable,
        stim_state: str,
    ) -> bool:
        """Play an instruction MP3 and frame-count through its duration
        plus ``gap_after`` seconds of silence.

        Returns False if aborted.
        """
        mp3_dur = self._audio.get_instruction_duration(name)
        if mp3_dur <= 0.0:
            # File missing or failed to load — still leave a sensible pause
            mp3_dur = 1.5
        total = mp3_dur + gap_after
        _phase(phase, total)
        _stim(stim_state)
        self._audio.play_instruction(name)
        self._events.log(event_type, subject, shape_name, str(rep))

        for _ in range(self._win.duration_to_frames(total)):
            if self._abort:
                self._audio.stop_instruction(name)
                return False
            self._win.flip()
        return True

    def _post_measurement_instruction(
        self,
        subject: str,
        shape_name: str,
        rep: int,
        is_last_shape: bool,
        is_last_queue_item: bool,
        _phase: Callable,
        _stim: Callable,
    ) -> None:
        """Play the context-dependent post-measurement MP3."""
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

    # --- Block mode (one shape per run) ---------------------------------

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
        on_recording_started: Callable = None,
        on_recording_saved: Callable = None,
        start_from_cycle: int = 1,
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
            on_recording_started: Callback(video_path_str) when camera starts recording.
            on_recording_saved: Callback(video_path_str) when recording completes.
            start_from_cycle: 1-based cycle to resume from. When > 1, skips
                training and instruction phases and jumps straight to the
                measurement loop at that cycle.

        Returns True if completed normally, False if aborted.
        """
        t = self._timing
        self._abort = False
        resuming = start_from_cycle > 1

        # Normalize shape to a string name (supports Shape enum or plain string)
        shape_name = shape.value if hasattr(shape, "value") else str(shape)

        # Total beeps: 2 per training rep (start+end) + 2 per imagination cycle
        total_beeps = (t.training_repetitions * 2) + (t.imagination_cycles * 2)
        # When resuming, skip beep count for training + already-completed cycles
        beep_counter = 0
        if resuming:
            beep_counter = (t.training_repetitions * 2) + ((start_from_cycle - 1) * 2)

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

        if resuming:
            self._events.log(
                "TRIAL_RESUME", subject, shape_name, str(rep),
                f"from_cycle={start_from_cycle}",
            )
            self.last_completed_cycle = start_from_cycle - 1
        else:
            self._events.log("TRIAL_START", subject, shape_name, str(rep))
            self.last_completed_cycle = 0

        # ===== Training + Instruction phases (skipped on resume) =====
        if not resuming:
            if not self._run_training_reps(
                shape_name, subject, rep, _phase, _stim, _beep,
            ):
                return False

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
        fps = self._camera_fps()
        total_frames_recorded = 0

        for i in range(start_from_cycle - 1, t.imagination_cycles):
            if self._abort:
                return False

            cycle_num = i + 1
            cycle_video_path = video_path_factory(cycle_num)

            frames = self._run_measurement_cycle(
                shape_name, subject, rep, f"cycle_{cycle_num}",
                cycle_video_path, fps, _phase, _beep,
                on_recording_started, on_recording_saved,
            )
            if frames is None:
                return False
            total_frames_recorded += frames

            # Cycle fully completed (recording saved + end beep played)
            self.last_completed_cycle = cycle_num

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
        self._post_measurement_instruction(
            subject, shape_name, rep, is_last_shape, is_last_queue_item,
            _phase, _stim,
        )

        _stim("idle")
        self._events.log(
            "TRIAL_END", subject, shape_name, str(rep),
            f"total_frames={total_frames_recorded} cycles={t.imagination_cycles}",
        )
        return True

    # --- Interleaving mode (one whole subject turn per run) -------------

    def run_interleaved(
        self,
        cycle_sequence: List[str],
        training_shapes: List[str],
        subject: str,
        rep: int,
        video_path_factory: Callable[[int], "Path"],
        is_last_queue_item: bool = False,
        on_phase_change: Callable = None,
        on_stimulus_update: Callable = None,
        on_beep_progress: Callable = None,
        on_recording_started: Callable = None,
        on_recording_saved: Callable = None,
        start_from_cycle: int = 1,
    ) -> bool:
        """Execute one whole subject turn with interleaved imagination cycles.

        Sequence: "observe the shapes" MP3 → training for every shape →
        close-eyes MP3 → for each entry of ``cycle_sequence``:
        "Imagine a <shape>" MP3 → gap → start beep → recording delay →
        camera recording → end beep → inter-cycle delay.

        Args:
            cycle_sequence: Pre-shuffled list of shape names, one entry
                per imagination cycle (e.g. ['circle', 'triangle', ...]).
            training_shapes: Unique shape names in presentation order for
                the up-front training phase.
            subject: Subject name.
            rep: Repetition number.
            video_path_factory: Callable(global_cycle_number) -> Path.
                Global cycle numbers are 1-based indices into
                ``cycle_sequence``.
            is_last_queue_item: True if this is the very last item in the
                session (controls the closing MP3).
            start_from_cycle: 1-based global cycle to resume from. When
                > 1, skips the observe/training/close-eyes phases and
                jumps straight to that cycle (pause/resume support).

        ``last_completed_cycle`` counts completed entries of
        ``cycle_sequence`` (global, not per-shape).

        Returns True if completed normally, False if aborted.
        """
        t = self._timing
        self._abort = False
        resuming = start_from_cycle > 1
        n_cycles = len(cycle_sequence)
        turn_label = "interleaved"

        # Total beeps: training for every shape + 2 per imagination cycle
        total_beeps = (
            len(training_shapes) * t.training_repetitions * 2 + n_cycles * 2
        )
        beep_counter = 0
        if resuming:
            beep_counter = (
                len(training_shapes) * t.training_repetitions * 2
                + (start_from_cycle - 1) * 2
            )

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

        if resuming:
            self._events.log(
                "TRIAL_RESUME", subject, turn_label, str(rep),
                f"from_cycle={start_from_cycle}",
            )
            self.last_completed_cycle = start_from_cycle - 1
        else:
            self._events.log(
                "TRIAL_START", subject, turn_label, str(rep),
                f"sequence={','.join(cycle_sequence)}",
            )
            self.last_completed_cycle = 0

        # ===== Observe + training + close-eyes (skipped on resume) =====
        if not resuming:
            # --- "Observe the screen and memorize the shapes" ---
            if not self._play_instruction_and_wait(
                "observe_shapes", TrialPhase.INSTRUCTION_OBSERVE,
                gap_after=1.0, subject=subject, shape_name=turn_label,
                rep=rep, event_type="INSTRUCTION_OBSERVE_SHAPES",
                _phase=_phase, _stim=_stim,
                stim_state="instruction:observe_shapes",
            ):
                return False

            # --- Training phase for every shape ---
            for shape_name in training_shapes:
                if not self._run_training_reps(
                    shape_name, subject, rep, _phase, _stim, _beep,
                ):
                    return False

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

            # ===== Instruction: close your eyes =====
            if self._abort:
                return False

            _phase(TrialPhase.INSTRUCTION_CLOSE_EYES, 5.0)
            _stim("instruction:close_eyes")
            self._audio.play_instruction("close_your_eyes")
            self._events.log("INSTRUCTION_CLOSE_EYES", subject, turn_label, str(rep))

            # Wait 5 seconds (frame-counted)
            _phase(TrialPhase.INSTRUCTION_WAIT, 5.0)
            for _ in range(self._n_close_eyes_wait):
                if self._abort:
                    return False
                self._win.flip()

        # ===== Measurement: interleaved imagination cycles =====
        if self._abort:
            return False

        fps = self._camera_fps()
        total_frames_recorded = 0

        for i in range(start_from_cycle - 1, n_cycles):
            if self._abort:
                return False

            cycle_num = i + 1
            shape_name = cycle_sequence[i]

            # --- "Imagine a <shape>" spoken prompt + gap before beep ---
            if not self._play_instruction_and_wait(
                f"imagine_{shape_name}", TrialPhase.MEASUREMENT_IMAGINE_PROMPT,
                gap_after=t.imagine_prompt_gap, subject=subject,
                shape_name=shape_name, rep=rep,
                event_type="INSTRUCTION_IMAGINE_PROMPT",
                _phase=_phase, _stim=_stim,
                stim_state=f"instruction:imagine_{shape_name}",
            ):
                return False

            _stim("recording")
            cycle_video_path = video_path_factory(cycle_num)

            frames = self._run_measurement_cycle(
                shape_name, subject, rep, f"seq_{cycle_num}",
                cycle_video_path, fps, _phase, _beep,
                on_recording_started, on_recording_saved,
            )
            if frames is None:
                return False
            total_frames_recorded += frames

            # Cycle fully completed (recording saved + end beep played)
            self.last_completed_cycle = cycle_num

            # --- Inter-imagination delay (skip after last cycle) ---
            if i < n_cycles - 1:
                _phase(
                    TrialPhase.MEASUREMENT_INTER_DELAY,
                    t.inter_imagination_delay,
                )
                for _ in range(self._n_inter_delay):
                    if self._abort:
                        return False
                    self._win.flip()

        # ===== Post-measurement instruction (whole turn is done) =====
        self._post_measurement_instruction(
            subject, turn_label, rep,
            is_last_shape=True, is_last_queue_item=is_last_queue_item,
            _phase=_phase, _stim=_stim,
        )

        _stim("idle")
        self._events.log(
            "TRIAL_END", subject, turn_label, str(rep),
            f"total_frames={total_frames_recorded} cycles={n_cycles}",
        )
        return True
