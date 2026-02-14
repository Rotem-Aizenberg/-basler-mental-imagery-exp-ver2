"""Thread-safe CSV event logger with ms-precision timestamps."""

from __future__ import annotations

import csv
import threading
import time
from pathlib import Path
from typing import Optional


class EventLogger:
    """Append-only CSV logger for experiment events.

    Each row: timestamp_s, elapsed_ms, event_type, subject, shape, rep, detail

    All public methods are thread-safe.
    """

    HEADER = [
        "timestamp_s", "elapsed_ms", "event_type",
        "subject", "shape", "rep", "detail",
    ]

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.HEADER)
        self._file.flush()

    def start_clock(self) -> None:
        """Set the reference time for elapsed_ms calculation."""
        self._start_time = time.perf_counter()

    def log(
        self,
        event_type: str,
        subject: str = "",
        shape: str = "",
        rep: str = "",
        detail: str = "",
    ) -> None:
        """Append one event row (thread-safe)."""
        now = time.perf_counter()
        elapsed = (now - self._start_time) * 1000 if self._start_time else 0.0
        with self._lock:
            self._writer.writerow([
                f"{now:.6f}",
                f"{elapsed:.3f}",
                event_type,
                subject,
                shape,
                rep,
                detail,
            ])
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()
