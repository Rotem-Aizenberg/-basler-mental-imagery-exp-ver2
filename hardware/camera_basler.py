"""Basler pypylon camera backend.

Adapts proven patterns from basler_camera_test.py:
- Lazy pypylon import
- TlFactory.GetInstance() for enumeration
- InstantCamera with CreateDevice
- ROI centering with even offsets
- Auto-exposure/gain off before manual values
- GrabStrategy_LatestImageOnly
- MJPG codec via OpenCV VideoWriter
- IsGrabbing/IsOpen cleanup guards
"""

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


class BaslerCamera(CameraBackend):
    """Basler acA1440-220um USB3 backend via pypylon."""

    def __init__(self):
        self._pylon = None
        self._camera = None
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

    # --- Connection ---

    def connect(self, settings: CameraSettings) -> None:
        # Lazy import
        try:
            from pypylon import pylon
            self._pylon = pylon
        except ImportError as e:
            raise RuntimeError(
                "pypylon not installed. Install Basler Pylon SDK then: pip install pypylon"
            ) from e

        self._settings = settings
        tlf = self._pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()

        if not devices:
            raise RuntimeError(
                "No Basler cameras detected. Check USB 3.0 connection."
            )

        # Find target by serial or use first
        target = None
        for d in devices:
            if d.GetSerialNumber() == settings.expected_serial:
                target = d
                break
        if target is None:
            logger.warning(
                "Target serial %s not found, using first camera",
                settings.expected_serial,
            )
            target = devices[0]

        self._camera = self._pylon.InstantCamera(tlf.CreateDevice(target))
        self._camera.Open()

        if not self._camera.IsOpen():
            raise RuntimeError("Camera failed to open")

        self._apply_settings(settings)
        logger.info(
            "Connected to %s (S/N: %s)",
            target.GetModelName(),
            target.GetSerialNumber(),
        )
        # Start continuous grab thread for live preview
        self._grab_stop.clear()
        self._grab_thread = threading.Thread(
            target=self._grab_loop, daemon=True,
        )
        self._grab_thread.start()

    def _apply_settings(self, s: CameraSettings) -> None:
        cam = self._camera

        # ROI: reset offsets, set size, then apply offset
        cam.OffsetX.SetValue(0)
        cam.OffsetY.SetValue(0)
        cam.Width.SetValue(s.width)
        cam.Height.SetValue(s.height)

        # Apply offsets (must be multiples of 4)
        off_x = (s.offset_x // 4) * 4
        cam.OffsetX.SetValue(off_x)

        off_y = (s.offset_y // 4) * 4
        cam.OffsetY.SetValue(off_y)

        # Pixel format
        cam.PixelFormat.SetValue(s.pixel_format)

        # Exposure (disable auto first)
        try:
            cam.ExposureAuto.SetValue("Off")
        except Exception:
            pass
        cam.ExposureTime.SetValue(s.exposure_time_us)

        # Gain (disable auto first)
        try:
            cam.GainAuto.SetValue("Off")
        except Exception:
            pass
        cam.Gain.SetValue(s.gain_db)

        # Frame rate
        try:
            cam.AcquisitionFrameRateEnable.SetValue(True)
            cam.AcquisitionFrameRate.SetValue(s.target_frame_rate)
        except Exception:
            logger.warning("Could not set frame rate, using max achievable")

        # Gamma
        try:
            cam.Gamma.SetValue(s.gamma)
        except Exception:
            logger.warning("Could not set Gamma")

    def _grab_loop(self) -> None:
        """Continuously grab frames for preview when not recording.

        Uses StartGrabbingMax(1) for single-frame grabs at ~20 fps
        to keep the preview alive without interfering with recording.
        """
        while not self._grab_stop.is_set():
            if self._recording:
                # Recording thread handles grabbing — sleep briefly
                time.sleep(0.05)
                continue
            if not self.is_connected():
                break
            try:
                self._camera.StartGrabbingMax(1)
                result = self._camera.RetrieveResult(
                    1000, self._pylon.TimeoutHandling_Return,
                )
                if result and result.GrabSucceeded():
                    frame = result.GetArray().copy()
                    with self._frame_lock:
                        self._latest_frame = frame
                if result:
                    result.Release()
            except Exception:
                time.sleep(0.05)

    def disconnect(self) -> None:
        self._grab_stop.set()
        if self._grab_thread is not None:
            self._grab_thread.join(timeout=2.0)
            self._grab_thread = None
        if self._camera is not None:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                if self._camera.IsOpen():
                    self._camera.Close()
            except Exception as e:
                logger.warning("Error during camera disconnect: %s", e)
            self._camera = None
        logger.info("Camera disconnected")

    def is_connected(self) -> bool:
        return self._camera is not None and self._camera.IsOpen()

    # --- Frame grabbing ---

    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected():
            return None
        try:
            self._camera.StartGrabbingMax(1)
            result = self._camera.RetrieveResult(
                5000, self._pylon.TimeoutHandling_ThrowException
            )
            if result.GrabSucceeded():
                frame = result.GetArray().copy()
                result.Release()
                return frame
            result.Release()
        except Exception as e:
            logger.error("Frame grab failed: %s", e)
        return None

    def get_preview_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    # --- Recording ---

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
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(
            str(output_path), fourcc, fps,
            (s.width, s.height), isColor=False,
        )
        if not writer.isOpened():
            logger.error("Failed to open VideoWriter at %s", output_path)
            self._recording = False
            return

        self._camera.StartGrabbing(self._pylon.GrabStrategy_LatestImageOnly)

        try:
            while not self._stop_event.is_set():
                result = self._camera.RetrieveResult(
                    1000, self._pylon.TimeoutHandling_Return
                )
                if result and result.GrabSucceeded():
                    frame = result.GetArray()
                    writer.write(frame)
                    self._frames_captured += 1
                    with self._frame_lock:
                        self._latest_frame = frame.copy()
                if result:
                    result.Release()
        finally:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
            writer.release()
            self._recording = False

    def stop_recording(self) -> int:
        self._stop_event.set()
        if self._record_thread is not None:
            self._record_thread.join(timeout=5.0)
        return self._frames_captured

    def is_recording(self) -> bool:
        return self._recording

    # --- Info ---

    def get_device_info(self) -> dict:
        if not self.is_connected():
            return {}
        info = self._camera.GetDeviceInfo()
        result = {
            "model": info.GetModelName(),
            "serial": info.GetSerialNumber(),
            "device_class": info.GetDeviceClass(),
        }
        try:
            result["firmware"] = info.GetFirmwareVersion()
        except Exception:
            pass
        return result
