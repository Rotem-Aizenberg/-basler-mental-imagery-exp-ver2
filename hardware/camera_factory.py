"""Camera backend factory."""

from __future__ import annotations

from typing import Tuple

from .camera_base import CameraBackend


def create_camera(dev_mode: bool = False) -> CameraBackend:
    """Return the appropriate camera backend.

    Args:
        dev_mode: If True, use webcam fallback. Otherwise use Basler.
    """
    if dev_mode:
        from .camera_webcam import WebcamCamera
        return WebcamCamera()
    else:
        from .camera_basler import BaslerCamera
        return BaslerCamera()


def detect_basler() -> Tuple[bool, str]:
    """Check if a Basler camera is available.

    Returns:
        (detected, detail): True + model name if found, False + reason otherwise.
    """
    try:
        from pypylon import pylon
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        if devices:
            model = devices[0].GetModelName()
            serial = devices[0].GetSerialNumber()
            return True, f"{model} (S/N: {serial})"
        return False, "No Basler cameras detected"
    except ImportError:
        return False, "pypylon not installed"
    except Exception as e:
        return False, str(e)
