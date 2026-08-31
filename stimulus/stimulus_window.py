"""PsychoPy-based fullscreen stimulus window.

Wraps ``psychopy.visual.Window`` with convenience methods for shape
display, frame-counting, and ``callOnFlip`` registration.

IMPORTANT: Must be created and used on the same thread (OpenGL context
is thread-bound).  In this codebase, that is the engine QThread.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict

from core.enums import Shape

logger = logging.getLogger(__name__)


class StimulusWindow:
    """PsychoPy fullscreen window for stimulus presentation.

    Provides vsync-locked flipping and ``callOnFlip`` for hardware-level
    audio/visual synchronisation.
    """

    def __init__(self, screen: int = 0, dev_mode: bool = False):
        from psychopy import visual, monitors

        # Create a monitor profile with the actual screen resolution so
        # PsychoPy doesn't fall back to a stale/default [800, 600] profile.
        # This makes the experiment portable across PCs without needing
        # manual PsychoPy Monitor Center configuration.
        screen_res = self._detect_screen_resolution(screen)
        mon = monitors.Monitor("experiment_monitor")
        mon.setSizePix(screen_res)
        mon.setWidth(53)    # approximate cm — irrelevant for "height" units
        mon.setDistance(60)  # approximate cm — irrelevant for "height" units
        mon.saveMon()

        self._win = visual.Window(
            size=screen_res,
            fullscr=True,
            screen=screen,
            monitor=mon,
            color=[-1, -1, -1],   # black
            units="height",
            waitBlanking=True,
            allowGUI=False,
            checkTiming=False,  # we measure frame rate ourselves below
        )
        self._stims: Dict[str, object] = {}

        # Raise process/thread scheduling priority so Windows doesn't
        # preempt the flip loop (fewer dropped frames -> smoother
        # stimulus transitions).  Reverted in close().
        try:
            from psychopy import core as _core
            _core.rush(True, realtime=False)
            logger.info("Raised process priority for stimulus timing")
        except Exception as e:
            logger.debug("Could not raise process priority: %s", e)

        # Show "Get ready" message while measuring frame rate
        self._show_message("Get ready")
        self._frame_rate = self._measure_frame_rate(dev_mode)
        # Clear the message — show black screen
        self._win.flip()

    @staticmethod
    def _detect_screen_resolution(screen: int) -> list:
        """Detect the resolution of the target screen.

        Tries multiple backends (Qt, tkinter, ctypes) so this works on
        any PC regardless of what GUI toolkit is available.
        """
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                screens = app.screens()
                if screen < len(screens):
                    geo = screens[screen].size()
                    res = [geo.width(), geo.height()]
                    logger.info("Screen %d resolution (Qt): %s", screen, res)
                    return res
        except Exception:
            pass

        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            res = [root.winfo_screenwidth(), root.winfo_screenheight()]
            root.destroy()
            logger.info("Screen resolution (tkinter): %s", res)
            return res
        except Exception:
            pass

        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            res = [user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)]
            logger.info("Screen resolution (ctypes): %s", res)
            return res
        except Exception:
            pass

        logger.warning("Could not detect screen resolution, using 1920x1080 default")
        return [1920, 1080]

    def _show_message(self, text: str) -> None:
        """Display a text message on the stimulus window."""
        from psychopy import visual as vis
        msg = vis.TextStim(
            self._win, text=text, color="white",
            height=0.06, units="height",
        )
        msg.draw()
        self._win.flip()

    def _measure_frame_rate(self, dev_mode: bool) -> float:
        """Measure the actual display refresh rate manually.

        Uses a simple frame-counting approach instead of PsychoPy's
        built-in ``getActualFrameRate()`` which displays unwanted text
        on the participant screen.
        """
        if dev_mode:
            logger.info("Dev mode: skipping frame rate measurement, assuming 60 Hz")
            return 60.0

        import time

        # Manual measurement: flip frames and count timing
        n_frames = 100
        n_warmup = 10

        try:
            # Warm-up flips
            for _ in range(n_warmup):
                self._win.flip()

            # Timed flips
            t0 = time.perf_counter()
            for _ in range(n_frames):
                self._win.flip()
            elapsed = time.perf_counter() - t0

            rate = n_frames / elapsed
            # Sanity check: should be between 30 and 240 Hz
            if 30.0 <= rate <= 240.0:
                logger.info("Measured display frame rate: %.2f Hz", rate)
                return rate
            else:
                logger.warning(
                    "Measured frame rate %.2f Hz out of range, assuming 60 Hz", rate,
                )
                return 60.0
        except Exception as e:
            logger.warning("Frame rate measurement failed: %s, assuming 60 Hz", e)
            return 60.0

    @property
    def frame_rate(self) -> float:
        """Display refresh rate in Hz."""
        return self._frame_rate

    @property
    def frame_duration(self) -> float:
        """Duration of one frame in seconds."""
        return 1.0 / self._frame_rate

    def duration_to_frames(self, duration_sec: float) -> int:
        """Convert a duration in seconds to the nearest frame count (>= 1)."""
        return max(1, round(duration_sec * self._frame_rate))

    def prepare_shape(self, shape: Shape, color: str = "white") -> None:
        """Pre-build a PsychoPy stimulus for the given shape."""
        from stimulus.shape_renderer import create_shape_stim
        self._stims[shape.value] = create_shape_stim(self._win, shape, color=color)
        logger.debug("Prepared stimulus: %s (color=%s)", shape.value, color)

    def prepare_image(self, name: str, image_path: str) -> None:
        """Pre-build a PsychoPy ImageStim for an image file."""
        from stimulus.shape_renderer import create_image_stim
        self._stims[name] = create_image_stim(self._win, image_path)
        logger.debug("Prepared image stimulus: %s -> %s", name, image_path)

    def draw_shape(self, shape_name: str) -> None:
        """Draw a pre-built shape to the back-buffer (does NOT flip)."""
        stim = self._stims.get(shape_name)
        if stim:
            stim.draw()

    def call_on_flip(self, func, *args, **kwargs) -> None:
        """Register a callback to fire at the exact vsync moment.

        ``func(*args, **kwargs)`` is called immediately after the
        next ``flip()`` — i.e. at the instant the new frame becomes
        visible.  This is the mechanism for sub-ms audio/visual sync.
        """
        self._win.callOnFlip(func, *args, **kwargs)

    def flip(self) -> float:
        """Swap buffers, wait for vsync, execute callOnFlip callbacks.

        Returns:
            PsychoPy flip timestamp (seconds since Window creation).
        """
        return self._win.flip()

    def close(self) -> None:
        """Close the PsychoPy window and release the OpenGL context."""
        try:
            from psychopy import core as _core
            _core.rush(False)
        except Exception:
            pass
        self._stims.clear()
        if self._win is None:
            return
        try:
            self._win.close()
        except Exception:
            pass
        self._win = None
