"""Cross-session persistent memory stored as JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Store relative to the codebase root for portability
_MEMORY_DIR = Path(__file__).resolve().parent.parent / ".app_memory"
_MEMORY_FILE = _MEMORY_DIR / "memory.json"


class AppMemory:
    """Persistent cross-session memory for the experiment application.

    Stores last-used output folder, subject history, settings, and
    camera settings in a JSON file within the codebase directory.
    """

    def __init__(self):
        self.last_output_folder: str = ""
        self.subject_history: List[str] = []
        self.last_settings: Dict = {}
        self.last_camera_settings: Dict = {}
        self.last_audio_device: str = ""
        self.last_screen_index: int = -1
        self.load()

    def load(self) -> None:
        """Load memory from disk, or initialize empty if not found."""
        if not _MEMORY_FILE.exists():
            return
        try:
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.last_output_folder = data.get("last_output_folder", "")
            self.subject_history = data.get("subject_history", [])
            self.last_settings = data.get("last_settings", {})
            self.last_camera_settings = data.get("last_camera_settings", {})
            self.last_audio_device = data.get("last_audio_device", "")
            self.last_screen_index = data.get("last_screen_index", -1)
            logger.info("App memory loaded from %s", _MEMORY_FILE)
        except Exception as e:
            logger.warning("Failed to load app memory: %s", e)

    def save(self) -> None:
        """Persist memory to disk."""
        try:
            _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "last_output_folder": self.last_output_folder,
                "subject_history": self.subject_history,
                "last_settings": self.last_settings,
                "last_camera_settings": self.last_camera_settings,
                "last_audio_device": self.last_audio_device,
                "last_screen_index": self.last_screen_index,
            }
            with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("App memory saved to %s", _MEMORY_FILE)
        except Exception as e:
            logger.warning("Failed to save app memory: %s", e)

    def add_subjects(self, names: List[str]) -> None:
        """Add subject names to history (deduplicated, preserving order)."""
        seen = set(self.subject_history)
        for name in names:
            if name and name not in seen:
                self.subject_history.append(name)
                seen.add(name)
        self.save()

    def get_subject_history(self) -> List[str]:
        """Return all previously-used subject names."""
        return list(self.subject_history)

    def update_settings(self, config_dict: dict) -> None:
        """Store last-used experiment settings."""
        self.last_settings = config_dict
        self.save()

    def update_camera_settings(self, camera_dict: dict) -> None:
        """Store last-used camera settings."""
        self.last_camera_settings = camera_dict
        self.save()
