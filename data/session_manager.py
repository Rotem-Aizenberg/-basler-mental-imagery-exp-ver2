"""Hierarchical output folder creation and session bookkeeping."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from config.settings import ExperimentConfig


class SessionManager:
    """Creates and manages the session output directory tree.

    Layout::

        outputs/session_YYYY-MM-DD_HH-MM-SS/
            session_log.xlsx
            session_config.json
            event_log.csv
            progress.json
            subjects/{name}/rep_{N}/{shape}/
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = (
            Path(config.output_base_dir) / f"session_{self.timestamp}"
        )

    def create_session_dirs(self, subjects: List[str]) -> Path:
        """Create the full directory hierarchy and return session_dir."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Subject sub-trees
        for name in subjects:
            for rep in range(1, self.config.repetitions + 1):
                for shape in self.config.shapes:
                    folder = (
                        self.session_dir / "subjects" / name
                        / f"rep_{rep}" / shape
                    )
                    folder.mkdir(parents=True, exist_ok=True)

        # Save config snapshot
        self.config.save(self.session_dir / "session_config.json")
        return self.session_dir

    def trial_video_path(
        self,
        subject: str,
        rep: int,
        shape: str,
        timestamp: str,
        shape_instance: int = 1,
        cycle: int = 0,
    ) -> Path:
        """Return the full path for a trial measurement video.

        Args:
            cycle: Imagination cycle number (1-based). If 0, uses legacy
                   single-file naming without cycle suffix.

        Generates informative filenames (extension matches the
        configured recording format):
            {subject}_{shape}_rep{rep}_shapeRep{inst}_cycle{cycle}_{timestamp}.avi
        """
        folder = (
            self.session_dir / "subjects" / subject
            / f"rep_{rep}" / shape
        )
        folder.mkdir(parents=True, exist_ok=True)
        ext = self._video_extension()
        if cycle > 0:
            filename = (
                f"{subject}_{shape}_rep{rep}_shapeRep{shape_instance}"
                f"_cycle{cycle}_{timestamp}{ext}"
            )
        else:
            filename = (
                f"{subject}_{shape}_rep{rep}_shapeRep{shape_instance}_{timestamp}{ext}"
            )
        return folder / filename

    def interleaved_video_path(
        self,
        subject: str,
        rep: int,
        shape: str,
        timestamp: str,
        shape_cycle: int,
        order: int,
    ) -> Path:
        """Return the video path for one interleaved imagination cycle.

        Files still live under the shape's folder so per-shape analysis
        is unchanged; the filename additionally encodes the global
        presentation order within the turn:

            {subject}_{shape}_rep{rep}_cycle{c}_order{k}_{timestamp}.avi

        Args:
            shape_cycle: 1-based cycle counter within this shape.
            order: 1-based global position in the shuffled sequence.
        """
        folder = (
            self.session_dir / "subjects" / subject
            / f"rep_{rep}" / shape
        )
        folder.mkdir(parents=True, exist_ok=True)
        ext = self._video_extension()
        filename = (
            f"{subject}_{shape}_rep{rep}_cycle{shape_cycle}"
            f"_order{order:02d}_{timestamp}{ext}"
        )
        return folder / filename

    def _video_extension(self) -> str:
        """File extension for the configured recording format."""
        try:
            from hardware.video_formats import get_extension
            return get_extension(self.config.camera.video_format)
        except Exception:
            return ".avi"

    # --- Crash-recovery progress file ---

    def save_progress(self, progress: dict) -> None:
        path = self.session_dir / "progress.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2)

    def load_progress(self) -> dict | None:
        path = self.session_dir / "progress.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
