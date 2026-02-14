"""OpenCV webcam fallback for development mode."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config.settings import CameraSettings
from .camera_base import CameraBackend

logger = logging.getLogger(__name__)


class WebcamCamera(CameraBackend):
    """Webcam-based camera backend for testing without Basler hardware."""

    def __init__(self):
        self._cap: Optional[cv2.VideoCapture] = None
        self._settings: Optional[CameraSettings] = None
        self._recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._frames_captured = 0
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()
        # Continuous grab thread for live preview even when not recording
        self._grab_thread: Optional[threading.Thread] = None
        self._grab_stop = threading.Event()

    def connect(self, settings: CameraSettings) -> None:
        self._settings = settings
        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            raise RuntimeError("No webcam available for dev mode")
        # Try to set resolution (best-effort)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)
        # Detect webcam native fps for recording playback
        native_fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._native_fps = native_fps if native_fps > 0 else 30.0
        logger.info(
            "Webcam connected (dev mode), native fps: %.1f", self._native_fps
        )
        # Start continuous grab thread for live preview
        self._grab_stop.clear()
        self._grab_thread = threading.Thread(
            target=self._grab_loop, daemon=True,
        )
        self._grab_thread.start()

    def _grab_loop(self) -> None:
        """Continuously grab frames for preview when not recording."""
        while not self._grab_stop.is_set():
            if self._recording:
                # Recording thread handles reads — sleep briefly
                time.sleep(0.05)
                continue
            if not self.is_connected():
                break
            ret, frame = self._cap.read()
            if ret:
                gray = self._to_gray_resized(frame)
                with self._frame_lock:
                    self._latest_frame = gray
            else:
                time.sleep(0.01)

    def disconnect(self) -> None:
        self._grab_stop.set()
        if self._grab_thread is not None:
            self._grab_thread.join(timeout=2.0)
            self._grab_thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Webcam disconnected")

    def is_connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected():
            return None
        ret, frame = self._cap.read()
        if ret:
            return self._to_gray_resized(frame)
        return None

    def get_preview_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def start_recording(self, output_path: Path, fps: float) -> None:
        if self._recording:
            return
        self._stop_event.clear()
        self._frames_captured = 0
        self._recording = True
        self._record_thread = threading.Thread(
            target=self._record_loop,
            args=(output_path, fps),
            daemon=True,
        )
        self._record_thread.start()

    def _record_loop(self, output_path: Path, fps: float) -> None:
        s = self._settings
        # Use the webcam's native FPS for recording playback speed,
        # ignoring the requested fps (which is meant for Basler cameras)
        record_fps = getattr(self, '_native_fps', 30.0)
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(
            str(output_path), fourcc, record_fps,
            (s.width, s.height), isColor=False,
        )
        if not writer.isOpened():
            logger.error("Failed to open VideoWriter at %s", output_path)
            self._recording = False
            return

        logger.info(
            "Webcam recording started at %.1f fps to %s",
            record_fps, output_path,
        )

        try:
            while not self._stop_event.is_set():
                ret, frame = self._cap.read()
                if ret:
                    gray = self._to_gray_resized(frame)
                    writer.write(gray)
                    self._frames_captured += 1
                    with self._frame_lock:
                        self._latest_frame = gray.copy()
                else:
                    # Brief sleep to avoid busy-wait if read fails
                    time.sleep(0.01)
        finally:
            writer.release()
            self._recording = False
            logger.info(
                "Webcam recording stopped: %d frames captured", self._frames_captured
            )

    def stop_recording(self) -> int:
        self._stop_event.set()
        if self._record_thread is not None:
            self._record_thread.join(timeout=5.0)
        return self._frames_captured

    def is_recording(self) -> bool:
        return self._recording

    def get_device_info(self) -> dict:
        return {
            "model": "Webcam (dev mode)",
            "serial": "N/A",
            "device_class": "USB",
        }

    def _to_gray_resized(self, frame: np.ndarray) -> np.ndarray:
        """Convert BGR frame to grayscale and resize to configured ROI."""
        if len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        s = self._settings
        return cv2.resize(frame, (s.width, s.height))
