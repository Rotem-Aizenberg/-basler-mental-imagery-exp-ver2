"""Real-time Excel session log using openpyxl."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class ExcelLogger:
    """Maintains a session_log.xlsx with one row per completed trial.

    Columns: timestamp, subject, shape, rep, status, video_file, notes

    All public methods are thread-safe. The workbook is saved after
    every write to ensure data is not lost on crash.
    """

    HEADER = [
        "timestamp", "subject", "shape", "rep",
        "status", "video_file", "notes",
        "exposure_us", "gain_db", "fps",
        "offset_x", "offset_y", "gamma",
    ]

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._wb: Optional[object] = None
        self._ws: Optional[object] = None
        self._init_workbook()

    def _init_workbook(self) -> None:
        try:
            from openpyxl import Workbook
            self._wb = Workbook()
            self._ws = self._wb.active
            self._ws.title = "Session Log"
            self._ws.append(self.HEADER)
            # Auto-width for header
            for col_idx, header in enumerate(self.HEADER, 1):
                self._ws.column_dimensions[
                    chr(64 + col_idx)
                ].width = max(len(header) + 2, 15)
            self._wb.save(str(self._path))
        except ImportError:
            self._wb = None
            self._ws = None

    def log_trial(
        self,
        subject: str,
        shape: str,
        rep: int,
        status: str,
        video_file: str = "",
        notes: str = "",
        camera_settings: dict | None = None,
    ) -> None:
        """Append a trial result row and save immediately.

        Args:
            camera_settings: Optional dict with keys: exposure_us, gain_db,
                fps, offset_x, offset_y, gamma.
        """
        if self._ws is None:
            return
        cs = camera_settings or {}
        with self._lock:
            self._ws.append([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                subject,
                shape,
                rep,
                status,
                video_file,
                notes,
                cs.get("exposure_us", ""),
                cs.get("gain_db", ""),
                cs.get("fps", ""),
                cs.get("offset_x", ""),
                cs.get("offset_y", ""),
                cs.get("gamma", ""),
            ])
            self._wb.save(str(self._path))

    @property
    def available(self) -> bool:
        return self._wb is not None
