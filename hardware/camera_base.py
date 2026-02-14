"""Abstract camera backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from config.settings import CameraSettings


class CameraBackend(ABC):
    """Protocol that all camera backends must implement."""

    @abstractmethod
    def connect(self, settings: CameraSettings) -> None:
        """Connect to the camera and apply settings.

        Raises RuntimeError on failure.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect and release all resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if camera is open and ready."""

    @abstractmethod
    def grab_frame(self) -> Optional[np.ndarray]:
        """Grab a single frame. Returns None on failure."""

    @abstractmethod
    def start_recording(self, output_path: Path, fps: float) -> None:
        """Start recording frames to a video file.

        Frames are grabbed in a tight loop on the camera thread.
        """

    @abstractmethod
    def stop_recording(self) -> int:
        """Stop recording and return number of frames captured."""

    @abstractmethod
    def is_recording(self) -> bool:
        """Return True if currently recording."""

    @abstractmethod
    def get_preview_frame(self) -> Optional[np.ndarray]:
        """Return the latest frame for live preview (non-blocking)."""

    @abstractmethod
    def get_device_info(self) -> dict:
        """Return dict with model, serial, firmware, etc."""
