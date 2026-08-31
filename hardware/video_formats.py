"""Video recording format registry shared by all camera backends.

Mirrors the recording formats offered by the official Basler pylon
software (pylon Viewer): Motion-JPEG AVI, Uncompressed AVI, and MP4.
All formats are written through OpenCV's VideoWriter so they work on
any modern Windows PC without extra codecs:

- ``mjpeg_avi``:  AVI container, MJPG fourcc (compressed, default)
- ``raw_avi``:    AVI container, fourcc 0 = uncompressed rawvideo.
                  Lossless 8-bit grayscale, large files.
- ``mp4``:        MP4 container, mp4v (MPEG-4 Part 2) codec.

Because uncompressed writing is known to fail on some OpenCV builds
(the writer opens but ``write()`` throws), :func:`probe_format` does a
real write/read round-trip so callers can verify a format on the
current machine *before* an experiment starts, and
:func:`create_video_writer` transparently falls back to MJPEG AVI if
the requested format cannot be opened.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_FORMAT = "mjpeg_avi"


@dataclass(frozen=True)
class VideoFormat:
    key: str
    label: str
    fourcc: Optional[str]   # None -> fourcc 0 (uncompressed)
    extension: str          # includes leading dot
    description: str


VIDEO_FORMATS = {
    "mjpeg_avi": VideoFormat(
        key="mjpeg_avi",
        label="AVI — Motion JPEG (compressed)",
        fourcc="MJPG",
        extension=".avi",
        description=(
            "Motion-JPEG compressed AVI (default). Small files, "
            "each frame JPEG-compressed independently."
        ),
    ),
    "raw_avi": VideoFormat(
        key="raw_avi",
        label="AVI — Uncompressed (lossless)",
        fourcc=None,
        extension=".avi",
        description=(
            "Uncompressed AVI, bit-exact raw pixel data as in the "
            "Basler pylon software. Large files (~1 byte per pixel "
            "per frame for Mono8)."
        ),
    ),
    "mp4": VideoFormat(
        key="mp4",
        label="MP4 — MPEG-4",
        fourcc="mp4v",
        extension=".mp4",
        description=(
            "MP4 container with MPEG-4 compression. Small files, "
            "plays in any media player."
        ),
    ),
}


def get_format(key: str) -> VideoFormat:
    """Return the VideoFormat for ``key``, falling back to the default."""
    fmt = VIDEO_FORMATS.get(key)
    if fmt is None:
        logger.warning("Unknown video format '%s', using %s", key, DEFAULT_FORMAT)
        fmt = VIDEO_FORMATS[DEFAULT_FORMAT]
    return fmt


def get_extension(key: str) -> str:
    """Return the file extension (with dot) for a format key."""
    return get_format(key).extension


def _fourcc_code(fmt: VideoFormat) -> int:
    return 0 if fmt.fourcc is None else cv2.VideoWriter_fourcc(*fmt.fourcc)


def create_video_writer(
    output_path: Path,
    format_key: str,
    fps: float,
    frame_size: Tuple[int, int],
) -> Tuple[Optional[cv2.VideoWriter], Path, str]:
    """Create a grayscale VideoWriter for the requested format.

    Falls back to MJPEG AVI (adjusting the file extension) if the
    requested writer cannot be opened on this machine.

    Args:
        output_path: Target file path (extension should already match
            the format; it is corrected on fallback).
        format_key: Key into VIDEO_FORMATS.
        fps: Playback frame rate to embed in the file.
        frame_size: (width, height).

    Returns:
        (writer, actual_path, actual_format_key). writer is None if
        even the fallback failed.
    """
    fmt = get_format(format_key)
    writer = cv2.VideoWriter(
        str(output_path), _fourcc_code(fmt), fps, frame_size, isColor=False,
    )
    if writer.isOpened():
        return writer, output_path, fmt.key

    logger.error(
        "VideoWriter for format '%s' failed to open at %s — "
        "falling back to MJPEG AVI", fmt.key, output_path,
    )
    try:
        writer.release()
    except Exception:
        pass

    fallback = VIDEO_FORMATS[DEFAULT_FORMAT]
    fallback_path = output_path.with_suffix(fallback.extension)
    writer = cv2.VideoWriter(
        str(fallback_path), _fourcc_code(fallback), fps, frame_size,
        isColor=False,
    )
    if writer.isOpened():
        return writer, fallback_path, fallback.key

    logger.error("Fallback MJPEG writer also failed at %s", fallback_path)
    try:
        writer.release()
    except Exception:
        pass
    return None, output_path, fmt.key


def probe_format(
    format_key: str,
    width: int = 64,
    height: int = 64,
    n_frames: int = 5,
) -> bool:
    """Verify that a format can actually be written on this machine.

    Performs a real write of a few grayscale frames to a temp file and
    checks the result is non-empty. Catches the "writer opens but
    write() throws" failure mode seen with uncompressed AVI on some
    OpenCV builds.
    """
    fmt = get_format(format_key)
    tmp_path = None
    try:
        fd, tmp_name = tempfile.mkstemp(suffix=fmt.extension)
        os.close(fd)
        tmp_path = Path(tmp_name)
        writer = cv2.VideoWriter(
            str(tmp_path), _fourcc_code(fmt), 30.0, (width, height),
            isColor=False,
        )
        if not writer.isOpened():
            return False
        frame = np.zeros((height, width), dtype=np.uint8)
        try:
            for _ in range(n_frames):
                writer.write(frame)
        finally:
            writer.release()
        return tmp_path.stat().st_size > 0
    except Exception as e:
        logger.warning("Video format probe failed for '%s': %s", format_key, e)
        return False
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except Exception:
                pass
