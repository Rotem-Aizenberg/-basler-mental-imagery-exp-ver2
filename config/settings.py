"""Experiment configuration with JSON persistence and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


@dataclass
class CameraSettings:
    """Camera hardware parameters (mirrors basler_camera_test.py CameraConfig)."""
    model_name: str = "acA1440-220um"
    expected_serial: str = "40034984"
    width: int = 128
    height: int = 128
    pixel_format: str = "Mono8"
    exposure_time_us: float = 1000.0
    gain_db: float = 17.7
    target_frame_rate: float = 500.0
    playback_fps: float = 500.0


@dataclass
class TimingSettings:
    """Trial timing parameters in seconds."""
    training_shape_duration: float = 1.5
    training_blank_duration: float = 0.5
    training_repetitions: int = 5
    close_eyes_cue_duration: float = 0.5
    measurement_beep_duration: float = 1.5
    measurement_silence_duration: float = 0.5
    measurement_repetitions: int = 5
    open_eyes_cue_duration: float = 0.5

    @property
    def training_phase_duration(self) -> float:
        return self.training_repetitions * (
            self.training_shape_duration + self.training_blank_duration
        )

    @property
    def measurement_phase_duration(self) -> float:
        return self.measurement_repetitions * (
            self.measurement_beep_duration + self.measurement_silence_duration
        )

    @property
    def total_trial_duration(self) -> float:
        return (
            self.training_phase_duration
            + self.close_eyes_cue_duration
            + self.measurement_phase_duration
            + self.open_eyes_cue_duration
        )


@dataclass
class AudioSettings:
    """Audio cue parameters."""
    sample_rate: int = 44100
    beep_frequency: float = 440.0
    beep_duration: float = 0.15
    beep_volume: float = 0.5


@dataclass
class ExperimentConfig:
    """Top-level experiment configuration with JSON load/save/validate."""
    shapes: List[str] = field(default_factory=lambda: [
        "circle", "square", "triangle", "star"
    ])
    repetitions: int = 5
    shape_reps_per_subsession: int = 1
    camera: CameraSettings = field(default_factory=CameraSettings)
    timing: TimingSettings = field(default_factory=TimingSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    dev_mode: bool = False
    output_base_dir: str = ""
    instruction_audio_dir: str = "external_instruction_recordings"

    def __post_init__(self):
        if not self.output_base_dir:
            self.output_base_dir = str(
                Path.home() / "lsci_experiment_output"
            )

    def validate(self) -> List[str]:
        """Return list of validation error strings (empty = valid)."""
        errors = []
        if not self.shapes:
            errors.append("At least one shape must be selected.")
        if self.repetitions < 1:
            errors.append("Repetitions must be >= 1.")
        if self.shape_reps_per_subsession < 1:
            errors.append("Shape reps per sub-session must be >= 1.")
        if self.camera.width < 16 or self.camera.height < 16:
            errors.append("Camera ROI must be at least 16x16.")
        if self.camera.exposure_time_us <= 0:
            errors.append("Exposure time must be positive.")
        if self.camera.target_frame_rate <= 0:
            errors.append("Frame rate must be positive.")
        if self.timing.training_repetitions < 1:
            errors.append("Training repetitions must be >= 1.")
        if self.timing.measurement_repetitions < 1:
            errors.append("Measurement repetitions must be >= 1.")
        return errors

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        """Save config to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ExperimentConfig":
        """Load config from JSON, falling back to defaults for missing keys."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> "ExperimentConfig":
        cam_data = data.get("camera", {})
        cam = CameraSettings(**{
            k: v for k, v in cam_data.items()
            if k in CameraSettings.__dataclass_fields__
        })

        timing_data = data.get("timing", {})
        timing = TimingSettings(**{
            k: v for k, v in timing_data.items()
            if k in TimingSettings.__dataclass_fields__
        })

        audio_data = data.get("audio", {})
        audio = AudioSettings(**{
            k: v for k, v in audio_data.items()
            if k in AudioSettings.__dataclass_fields__
        })

        return cls(
            shapes=data.get("shapes", cls.__dataclass_fields__["shapes"].default_factory()),
            repetitions=data.get("repetitions", 5),
            shape_reps_per_subsession=data.get("shape_reps_per_subsession", 1),
            camera=cam,
            timing=timing,
            audio=audio,
            dev_mode=data.get("dev_mode", False),
            output_base_dir=data.get("output_base_dir", ""),
            instruction_audio_dir=data.get(
                "instruction_audio_dir", "external_instruction_recordings"
            ),
        )
