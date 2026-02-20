"""Top-level session orchestrator.

Runs on an ExperimentWorker QThread.  PsychoPy Window and AudioManager
are created on the engine thread because the OpenGL context is
thread-bound and audio should live alongside it.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import List, Optional

from config.settings import ExperimentConfig
from core.enums import ExperimentState, TrialPhase, Shape
from core.session_queue import SessionQueue
from hardware.camera_base import CameraBackend
from data.session_manager import SessionManager
from data.event_logger import EventLogger
from data.excel_logger import ExcelLogger
from utils.threading_utils import ExperimentWorker, AtomicFlag

logger = logging.getLogger(__name__)


class ExperimentEngine:
    """Orchestrates the entire experiment session.

    Lifecycle:
        1. setup() — creates session dirs, loggers, queue  (GUI thread)
        2. start() — launches the worker thread
        3. _run() — creates PsychoPy Window + AudioManager,
                     runs trials, closes PsychoPy        (engine thread)
        4. session_finished signal → GUI cleanup
    """

    def __init__(self, config: ExperimentConfig, camera: CameraBackend):
        self.config = config
        self.camera = camera
        self.session_mgr: Optional[SessionManager] = None
        self.event_logger: Optional[EventLogger] = None
        self.excel_logger: Optional[ExcelLogger] = None
        self.queue: Optional[SessionQueue] = None

        self._state = ExperimentState.IDLE
        self._worker: Optional[ExperimentWorker] = None
        self._protocol = None  # Set in _run() on engine thread
        self._win = None  # PsychoPy window reference for cleanup
        self._abort_flag = AtomicFlag()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._confirm_event = threading.Event()

        self._subjects: List[str] = []
        self._screen_index: int = 0
        self._start_time: Optional[datetime] = None

    @property
    def state(self) -> ExperimentState:
        return self._state

    @property
    def worker(self) -> Optional[ExperimentWorker]:
        return self._worker

    def setup(self, subjects: List[str], screen_index: int = 0) -> None:
        """Initialize session directories, loggers, and queue.

        PsychoPy objects are NOT created here — they must live on the
        engine thread (OpenGL context is thread-bound).

        Args:
            subjects: List of subject names.
            screen_index: Display index for the PsychoPy stimulus window.
        """
        self._subjects = subjects
        self._screen_index = screen_index
        self.session_mgr = SessionManager(self.config)
        session_dir = self.session_mgr.create_session_dirs(subjects)

        self.event_logger = EventLogger(session_dir / "event_log.csv")
        self.excel_logger = ExcelLogger(session_dir / "session_log.xlsx")

        # Determine stimulus names for the queue
        stim_cfg = self.config.stimulus
        use_images = stim_cfg.use_images and stim_cfg.image_paths
        if use_images:
            stim_names = [f"image_{i}" for i in range(len(stim_cfg.image_paths))]
        else:
            stim_names = self.config.shapes

        self.queue = SessionQueue(
            subjects,
            self.config.repetitions,
            stim_names,
            shape_reps_per_subsession=self.config.shape_reps_per_subsession,
            use_raw_names=use_images,
        )
        self._state = ExperimentState.IDLE
        logger.info("Engine setup complete. Session dir: %s", session_dir)

    def reset(self) -> None:
        """Reset all state for a clean start after stop.

        Ensures no leftover PsychoPy context or thread state prevents restart.
        Forces garbage collection of OpenGL resources to prevent pyglet's
        'Unable to share contexts' error on Windows.
        """
        if self._worker is not None:
            if self._worker.isRunning():
                self._worker.wait(10000)  # Wait up to 10s for thread to finish
            self._worker = None

        self._protocol = None
        self._win = None

        # Force garbage collection to release pyglet/OpenGL contexts
        import gc
        gc.collect()

        # Brief delay to let OpenGL driver fully release resources
        import time
        time.sleep(0.5)

        self._abort_flag.clear()
        self._pause_event.set()
        self._confirm_event.clear()
        self._state = ExperimentState.IDLE

    def start(self) -> ExperimentWorker:
        """Launch the experiment worker thread."""
        self.reset()
        self._worker = ExperimentWorker(self._run)
        self._state = ExperimentState.RUNNING
        self._worker.start()
        return self._worker

    def pause(self) -> None:
        """Pause the experiment — immediately stops the current trial.

        The current trial's recording is discarded. The operator can
        then Retry (restart the current shape) or Stop (abort session).
        """
        self._pause_event.clear()
        self._state = ExperimentState.PAUSED
        # Immediately abort the current trial so it doesn't continue
        if self._protocol:
            self._protocol.request_abort()
        logger.info("Experiment paused — current trial interrupted")

    def resume(self) -> None:
        """Resume from pause (retries the current shape)."""
        # Re-enable the protocol for the next trial run
        if self._protocol:
            self._protocol._abort = False
        self._pause_event.set()
        self._state = ExperimentState.RUNNING
        logger.info("Experiment resumed")

    def confirm_next(self) -> None:
        """Operator confirms readiness for next subject."""
        self._confirm_event.set()

    def request_abort(self) -> None:
        """Request graceful abort of the entire session."""
        self._abort_flag.set()
        self._pause_event.set()   # Unblock if paused
        self._confirm_event.set() # Unblock if waiting
        if self._protocol:
            self._protocol.request_abort()
        logger.info("Abort requested")

    def retry_current(self) -> None:
        """Reset current queue item for retry on next loop iteration."""
        if self.queue:
            self.queue.reset_current()
        logger.info("Retry requested for current item")

    # --- Main loop (runs on QThread) ---

    def _run(self) -> None:
        """Main experiment loop on the engine thread.

        Creates PsychoPy Window and AudioManager here so that the
        OpenGL context and audio backend live on this thread.
        """
        w = self._worker
        stim_window = None
        self._start_time = datetime.now()

        try:
            # === Create PsychoPy resources on this thread ===
            from stimulus.stimulus_window import StimulusWindow
            from audio.audio_manager import AudioManager
            from core.trial_protocol import TrialProtocol

            stim_window = StimulusWindow(
                screen=self._screen_index,
                dev_mode=self.config.dev_mode,
            )
            self._win = stim_window

            # Prepare stimuli (shapes or images)
            stim_cfg = self.config.stimulus
            if stim_cfg.use_images and stim_cfg.image_paths:
                from stimulus.shape_renderer import hex_to_psychopy
                for i, img_path in enumerate(stim_cfg.image_paths):
                    stim_window.prepare_image(f"image_{i}", img_path)
            else:
                from stimulus.shape_renderer import hex_to_psychopy
                color = hex_to_psychopy(stim_cfg.color_hex)
                for shape_name in self.config.shapes:
                    shape_enum = Shape.from_string(shape_name)
                    stim_window.prepare_shape(shape_enum, color=color)

            audio = AudioManager(
                self.config.audio,
                instruction_dir=self.config.instruction_audio_dir,
            )

            # Pre-generate tones with frame-accurate durations.
            t = self.config.timing
            a = self.config.audio
            train_frames = stim_window.duration_to_frames(t.training_shape_duration)
            train_dur = train_frames * stim_window.frame_duration
            audio.pregenerate_training_tone(train_dur)

            start_beep_frames = stim_window.duration_to_frames(a.start_imagine_duration)
            start_beep_dur = start_beep_frames * stim_window.frame_duration
            audio.pregenerate_start_imagine_tone(start_beep_dur)

            end_beep_frames = stim_window.duration_to_frames(a.end_imagine_duration)
            end_beep_dur = end_beep_frames * stim_window.frame_duration
            audio.pregenerate_end_imagine_tone(end_beep_dur)

            self._protocol = TrialProtocol(
                t, a, audio, self.camera, self.event_logger, stim_window,
            )

            logger.info(
                "PsychoPy ready: %.1f Hz, frame=%.3f ms, "
                "training=%d frames (%.4fs), "
                "start_beep=%d frames (%.4fs), end_beep=%d frames (%.4fs)",
                stim_window.frame_rate, stim_window.frame_duration * 1000,
                train_frames, train_dur,
                start_beep_frames, start_beep_dur,
                end_beep_frames, end_beep_dur,
            )

            # === Run session ===
            self.event_logger.start_clock()
            self.event_logger.log("SESSION_START")
            w.state_changed.emit(ExperimentState.RUNNING)

            while not self.queue.is_done:
                if self._abort_flag.is_set:
                    break

                self._check_pause(w)
                if self._abort_flag.is_set:
                    break

                item = self.queue.current
                if item is None:
                    break

                # Wait for operator confirmation before each subject turn
                w.state_changed.emit(ExperimentState.WAITING_CONFIRM)
                w.progress_text.emit(
                    f"Waiting for confirmation: {item.subject} - Rep {item.rep}"
                )
                w.stimulus_update.emit("idle")
                self._state = ExperimentState.WAITING_CONFIRM
                self._confirm_event.clear()
                self._confirm_event.wait()
                if self._abort_flag.is_set:
                    break

                self._state = ExperimentState.RUNNING
                w.state_changed.emit(ExperimentState.RUNNING)

                # Determine context for instruction audio
                is_last_queue_item = (self.queue.current_index == self.queue.total - 1)
                total_shapes = len(item.shapes)

                # Total beeps per shape for progress tracking
                # Training beeps + 2 per imagination cycle (start + end)
                beeps_per_shape = (
                    self.config.timing.training_repetitions
                    + self.config.timing.imagination_cycles * 2
                )

                # Run all shapes for this queue item (with pause/retry support)
                all_ok = True
                shape_idx = 0
                while shape_idx < len(item.shapes):
                    if self._abort_flag.is_set:
                        all_ok = False
                        break

                    # Check if paused before starting shape — wait for resume
                    self._check_pause(w)
                    if self._abort_flag.is_set:
                        all_ok = False
                        break

                    shape = item.shapes[shape_idx]
                    is_last_shape = (shape_idx == len(item.shapes) - 1)

                    # Get string name for this shape/image
                    shape_name = shape.value if hasattr(shape, "value") else str(shape)

                    # Track shape instance for filename
                    shape_instance = sum(
                        1 for s in item.shapes[:shape_idx + 1]
                        if s == shape
                    )

                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # Per-cycle video path factory with cleanup tracking
                    cycle_videos = []

                    def make_video_path(cycle: int, _subj=item.subject,
                                        _rep=item.rep, _shape=shape_name,
                                        _ts=ts, _inst=shape_instance) -> "Path":
                        p = self.session_mgr.trial_video_path(
                            _subj, _rep, _shape, _ts,
                            shape_instance=_inst, cycle=cycle,
                        )
                        cycle_videos.append(p)
                        return p

                    w.progress_text.emit(
                        f"{item.subject} | Rep {item.rep} | {shape_name} "
                        f"({shape_idx + 1}/{total_shapes})"
                    )

                    # Beep progress: accumulate across shapes in this turn
                    base_beeps = shape_idx * beeps_per_shape
                    total_beeps_in_turn = total_shapes * beeps_per_shape

                    ok = self._protocol.run(
                        shape=shape,
                        subject=item.subject,
                        rep=item.rep,
                        video_path_factory=make_video_path,
                        is_last_shape=is_last_shape,
                        is_last_queue_item=is_last_queue_item,
                        on_phase_change=lambda ph, rem: w.phase_changed.emit(ph, rem),
                        on_stimulus_update=lambda st: w.stimulus_update.emit(st),
                        on_beep_progress=lambda cur, tot: w.beep_progress.emit(
                            base_beeps + cur, total_beeps_in_turn,
                        ),
                    )

                    if not ok:
                        # Trial was interrupted
                        if self._abort_flag.is_set:
                            # Full session abort — keep videos, mark aborted
                            video_names = ", ".join(
                                str(v.name) for v in cycle_videos
                            )
                            self.excel_logger.log_trial(
                                item.subject, shape_name, item.rep,
                                "aborted", video_names,
                            )
                            all_ok = False
                            break
                        else:
                            # Pause-interrupted: discard all cycle videos
                            for vp in cycle_videos:
                                self._discard_video(vp)
                            w.stimulus_update.emit("idle")
                            w.progress_text.emit(
                                "Paused — recording discarded. "
                                "Press Resume to restart this shape."
                            )
                            w.state_changed.emit(ExperimentState.PAUSED)
                            # Wait for resume (blocks until operator presses Resume)
                            self._check_pause(w)
                            if self._abort_flag.is_set:
                                all_ok = False
                                break
                            # Reset protocol for retry — DON'T advance shape_idx
                            if self._protocol:
                                self._protocol._abort = False
                            w.state_changed.emit(ExperimentState.RUNNING)
                            continue  # Retry same shape
                    else:
                        w.trial_completed.emit(
                            item.subject, shape_name, item.rep, "completed",
                        )
                        shape_idx += 1  # Advance to next shape

                if all_ok:
                    self.queue.advance()
                    w.queue_advanced.emit(self.queue.current_index)
                    self.session_mgr.save_progress(self.queue.to_progress_dict())

            # Final state
            end_time = datetime.now()
            if self._abort_flag.is_set:
                self._state = ExperimentState.ABORTED
                w.state_changed.emit(ExperimentState.ABORTED)
                self.event_logger.log("SESSION_ABORTED")
                session_status = "Aborted"
            else:
                self._state = ExperimentState.COMPLETED
                w.state_changed.emit(ExperimentState.COMPLETED)
                self.event_logger.log("SESSION_COMPLETED")
                session_status = "Completed"

            # Log to main experiment monitor
            self._log_to_monitor(end_time, session_status)

            # Save subjects to app memory
            self._save_to_app_memory()

        except Exception as e:
            logger.exception("Engine error")
            self._state = ExperimentState.ERROR
            w.error_occurred.emit(str(e))
            if self.event_logger:
                self.event_logger.log("SESSION_ERROR", detail=str(e))

        finally:
            # Clean up PsychoPy resources on this thread
            self._protocol = None
            if stim_window:
                try:
                    stim_window.close()
                except Exception:
                    pass
            self._win = None
            w.session_finished.emit()
            if self.event_logger:
                self.event_logger.close()

    @staticmethod
    def _discard_video(video_path) -> None:
        """Delete a partial/interrupted video file."""
        try:
            import os
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
                logger.info("Discarded interrupted recording: %s", video_path)
        except Exception as e:
            logger.warning("Could not delete video %s: %s", video_path, e)

    def _check_pause(self, w: ExperimentWorker) -> None:
        """Block until unpaused (or abort)."""
        if not self._pause_event.is_set():
            w.state_changed.emit(ExperimentState.PAUSED)
            self._pause_event.wait()

    def _log_to_monitor(self, end_time: datetime, status: str) -> None:
        """Log session summary to the main experiment monitor."""
        try:
            from data.main_experiment_monitor import MainExperimentMonitor

            cam = self.config.camera
            camera_summary = (
                f"{cam.width}x{cam.height} {cam.pixel_format} "
                f"{cam.exposure_time_us}us {cam.gain_db}dB {cam.target_frame_rate}fps"
            )

            monitor = MainExperimentMonitor(self.config.output_base_dir)
            monitor.log_session(
                start_time=self._start_time or end_time,
                end_time=end_time,
                status=status,
                participants=self._subjects,
                shapes=self.config.shapes,
                repetitions=self.config.repetitions,
                shape_reps_per_subsession=self.config.shape_reps_per_subsession,
                camera_summary=camera_summary,
                session_folder=str(self.session_mgr.session_dir),
            )
        except Exception as e:
            logger.warning("Failed to log to experiment monitor: %s", e)

    def _save_to_app_memory(self) -> None:
        """Save session data to persistent app memory."""
        try:
            from data.app_memory import AppMemory
            memory = AppMemory()
            memory.add_subjects(self._subjects)
            memory.last_output_folder = self.config.output_base_dir
            memory.update_settings(self.config.to_dict())
            memory.save()
        except Exception as e:
            logger.warning("Failed to save to app memory: %s", e)
