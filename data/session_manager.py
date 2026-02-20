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

        Generates informative AVI filenames:
            {subject}_{shape}_rep{rep}_shapeRep{inst}_cycle{cycle}_{timestamp}.avi
        """
        folder = (
            self.session_dir / "subjects" / subject
            / f"rep_{rep}" / shape
        )
        folder.mkdir(parents=True, exist_ok=True)
        if cycle > 0:
            filename = (
                f"{subject}_{shape}_rep{rep}_shapeRep{shape_instance}"
                f"_cycle{cycle}_{timestamp}.avi"
            )
        else:
            filename = (
                f"{subject}_{shape}_rep{rep}_shapeRep{shape_instance}_{timestamp}.avi"
            )
        return folder / filename

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
