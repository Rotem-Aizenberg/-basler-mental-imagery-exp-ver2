"""Audio playback manager using PsychoPy Sound for frame-accurate timing.

Pre-generates all tone buffers as PsychoPy Sound objects so that
``win.callOnFlip(audio.play, 'training')`` has zero allocation latency
and fires at the exact vsync moment.

Also loads MP3 instruction files for non-frame-critical playback
(close_your_eyes, starting, open_your_eyes, next_participant_please,
experiment_completed).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from config.settings import AudioSettings
from .tone_generator import generate_sine_tone

logger = logging.getLogger(__name__)

# Map instruction names to actual MP3 filenames
_INSTRUCTION_FILES = {
    "close_your_eyes": "close_your_eyes.mp3",
    "starting": "starting.mp3",
    "open_your_eyes": "Open_your_eyes.mp3",
    "next_participant_please": "next_participant_please.mp3",
    "experiment_completed": "We_have_successfully_completed.mp3",
}


class AudioManager:
    """Manages audio cue playback via PsychoPy Sound (PTB backend).

    All tones are pre-generated as numpy buffers and wrapped in
    PsychoPy Sound objects.  Use ``play(name)`` / ``stop(name)``
    which are safe to pass as ``win.callOnFlip()`` callbacks for
    vsync-synced onset and offset.

    Instruction MP3s are loaded separately for non-frame-critical playback.
    """

    def __init__(self, settings: AudioSettings, instruction_dir: str = ""):
        self._settings = settings
        self._sounds: Dict[str, object] = {}
        self._instructions: Dict[str, object] = {}
        self._sound_module = None
        self._available = False
        self._init_psychopy_sound()
        self._load_instructions(instruction_dir)

    def _init_psychopy_sound(self) -> None:
        try:
            # audio/__init__.py must have been imported first to set prefs
            from psychopy import sound
            self._sound_module = sound
            self._available = True
            logger.info("PsychoPy audio system initialized")
        except (ImportError, Exception) as e:
            logger.warning("PsychoPy audio not available: %s", e)
            self._available = False

    def _make_sound(self, buf: np.ndarray) -> object:
        """Wrap a 1-D float32 numpy buffer in a PsychoPy Sound object."""
        # PsychoPy expects (n_samples, n_channels) float array
        buf_2d = buf.astype(np.float64).reshape(-1, 1)
        return self._sound_module.Sound(
            value=buf_2d,
            sampleRate=self._settings.sample_rate,
        )

    def _load_instructions(self, instruction_dir: str) -> None:
        """Load MP3 instruction files via PsychoPy Sound."""
        if not self._available:
            return
        if not instruction_dir:
            # Default to external_instruction_recordings relative to codebase root
            instruction_dir = str(
                Path(__file__).resolve().parent.parent / "external_instruction_recordings"
            )

        base = Path(instruction_dir)
        if not base.is_absolute():
            base = Path(__file__).resolve().parent.parent / base

        loaded = 0
        for name, filename in _INSTRUCTION_FILES.items():
            mp3_path = base / filename
            if mp3_path.exists():
                try:
                    snd = self._sound_module.Sound(str(mp3_path))
                    self._instructions[name] = snd
                    loaded += 1
                    logger.debug("Loaded instruction: %s from %s", name, mp3_path)
                except Exception as e:
                    logger.warning(
                        "Failed to load instruction '%s' (%s): %s",
                        name, mp3_path, e,
                    )
            else:
                logger.warning("Instruction MP3 not found: %s", mp3_path)

        logger.info("Loaded %d/%d instruction MP3s", loaded, len(_INSTRUCTION_FILES))

    def pregenerate_training_tone(self, duration: float) -> None:
        """Pre-generate a continuous tone matching training shape display.

        The buffer is *exactly* ``duration`` seconds long so that audio
        and visual stimulus are inherently duration-matched (no drift).
        Call this after the PsychoPy window is created so that
        ``duration = n_frames * frame_duration`` is frame-accurate.
        """
        if not self._available:
            return
        s = self._settings
        self._sounds["training"] = self._make_sound(
            generate_sine_tone(
                s.beep_frequency, duration, s.sample_rate, s.beep_volume,
            )
        )
        logger.info(
            "Pre-generated training tone: %.4fs (%d samples)",
            duration, int(s.sample_rate * duration),
        )

    def pregenerate_measurement_tone(self, duration: float) -> None:
        """Pre-generate a continuous tone for measurement beep intervals."""
        if not self._available:
            return
        s = self._settings
        self._sounds["measurement"] = self._make_sound(
            generate_sine_tone(
                s.beep_frequency, duration, s.sample_rate, s.beep_volume,
            )
        )
        logger.info(
            "Pre-generated measurement tone: %.4fs (%d samples)",
            duration, int(s.sample_rate * duration),
        )

    @property
    def available(self) -> bool:
        return self._available

    def play(self, tone_name: str) -> None:
        """Play a pre-generated tone by name.

        Safe to use as a ``win.callOnFlip()`` callback for vsync-synced onset.
        """
        if not self._available:
            return
        snd = self._sounds.get(tone_name)
        if snd is None:
            logger.warning("Unknown tone: %s", tone_name)
            return
        try:
            snd.play()
        except Exception as e:
            logger.error("Audio playback error: %s", e)

    def stop(self, tone_name: str = None) -> None:
        """Stop a specific tone or all playing tones.

        Safe to use as a ``win.callOnFlip()`` callback for vsync-synced offset.
        """
        if not self._available:
            return
        if tone_name:
            snd = self._sounds.get(tone_name)
            if snd:
                try:
                    snd.stop()
                except Exception:
                    pass
        else:
            for snd in self._sounds.values():
                try:
                    snd.stop()
                except Exception:
                    pass

    def play_instruction(self, name: str) -> None:
        """Play an instruction MP3 (non-frame-critical).

        Blocks until playback starts, but does not block until complete.
        """
        if not self._available:
            return
        snd = self._instructions.get(name)
        if snd is None:
            logger.warning("Unknown instruction: %s", name)
            return
        try:
            snd.play()
        except Exception as e:
            logger.error("Instruction playback error for '%s': %s", name, e)

    def stop_instruction(self, name: str) -> None:
        """Stop a specific instruction sound."""
        if not self._available:
            return
        snd = self._instructions.get(name)
        if snd:
            try:
                snd.stop()
            except Exception:
                pass

    def get_instruction_duration(self, name: str) -> float:
        """Return the duration of an instruction MP3 in seconds."""
        snd = self._instructions.get(name)
        if snd is None:
            return 0.0
        try:
            return snd.getDuration()
        except Exception:
            return 0.0

    def has_instruction(self, name: str) -> bool:
        """Check if an instruction MP3 is loaded."""
        return name in self._instructions

    def test_output(self) -> bool:
        """Play a short test beep. Returns True if no error."""
        if not self._available:
            return False
        try:
            s = self._settings
            test_buf = generate_sine_tone(
                s.beep_frequency, 0.15, s.sample_rate, s.beep_volume,
            )
            test_snd = self._make_sound(test_buf)
            test_snd.play()
            time.sleep(0.2)
            test_snd.stop()
            return True
        except Exception as e:
            logger.error("Audio test failed: %s", e)
            return False
