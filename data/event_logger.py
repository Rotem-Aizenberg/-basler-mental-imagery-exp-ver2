"""Thread-safe CSV event logger with ms-precision timestamps.

Writes are asynchronous: ``log()`` only captures the timestamp and
enqueues the row (microseconds of work), while a background thread
performs the actual CSV write + flush.  This keeps disk I/O out of
timing-critical paths — ``log`` is registered as a PsychoPy
``callOnFlip`` callback, and any blocking I/O there (slow disk,
antivirus scan) would drop stimulus frames.
"""

from __future__ import annotations

import csv
import queue
import threading
import time
from pathlib import Path
from typing import Optional


class EventLogger:
    """Append-only CSV logger for experiment events.

    Each row: timestamp_s, elapsed_ms, event_type, subject, shape, rep, detail

    Timestamps are captured synchronously at the ``log()`` call; the
    file write happens on a dedicated background thread.
    """

    HEADER = [
        "timestamp_s", "elapsed_ms", "event_type",
        "subject", "shape", "rep", "detail",
    ]

    def __init__(self, path: Path):
        self._path = path
        self._start_time: Optional[float] = None
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.HEADER)
        self._file.flush()

        self._queue: "queue.Queue" = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(
            target=self._write_loop, daemon=True, name="EventLoggerWriter",
        )
        self._thread.start()

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
        """Enqueue one event row (non-blocking, safe inside callOnFlip).

        The timestamp is taken here, at call time, so timing precision
        is unaffected by the asynchronous write.
        """
        now = time.perf_counter()
        elapsed = (now - self._start_time) * 1000 if self._start_time else 0.0
        self._queue.put([
            f"{now:.6f}",
            f"{elapsed:.3f}",
            event_type,
            subject,
            shape,
            rep,
            detail,
        ])

    def _write_loop(self) -> None:
        """Drain the queue and write rows on the background thread."""
        while True:
            row = self._queue.get()
            if row is None:  # close sentinel
                break
            try:
                self._writer.writerow(row)
                # Drain any burst before flushing once
                while True:
                    try:
                        nxt = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is None:
                        self._file.flush()
                        return
                    self._writer.writerow(nxt)
                self._file.flush()
            except Exception:
                pass  # Never let logging kill the writer thread

    def close(self) -> None:
        """Flush all pending rows and close the file."""
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=5.0)
        try:
            self._file.flush()
            self._file.close()
        except Exception:
            pass
