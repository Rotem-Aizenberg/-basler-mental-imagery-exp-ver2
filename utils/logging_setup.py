"""Per-session file + console logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(session_dir: Path | None = None, level: int = logging.INFO) -> None:
    """Configure root logger with console + optional file handler.

    Args:
        session_dir: If provided, a ``session.log`` file handler is added.
        level: Logging level for both handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler (only add once)
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(fmt)
        root.addHandler(console)

    # File handler for session
    if session_dir is not None:
        session_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(
            session_dir / "session.log", encoding="utf-8"
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)
