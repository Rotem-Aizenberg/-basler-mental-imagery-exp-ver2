"""Enumerations for experiment states, trial phases, and shapes."""

from enum import Enum, auto


class ExperimentState(Enum):
    """Top-level experiment lifecycle states."""
    IDLE = auto()
    PREFLIGHT = auto()
    RUNNING = auto()
    PAUSED = auto()
    WAITING_CONFIRM = auto()   # Waiting for operator to confirm next subject
    COMPLETED = auto()
    ABORTED = auto()
    ERROR = auto()


class TrialPhase(Enum):
    """Phases within a single shape trial."""
    TRAINING_SHAPE = auto()        # Shape visible on screen + beep
    TRAINING_BLANK = auto()        # Blank screen between training flashes
    INSTRUCTION_CLOSE_EYES = auto()  # MP3: "close your eyes..."
    INSTRUCTION_WAIT = auto()      # Silence after close-eyes instruction
    INSTRUCTION_STARTING = auto()  # MP3: "starting"
    INSTRUCTION_READY = auto()     # Short wait after "starting"
    MEASUREMENT_BEEP = auto()      # Beep during measurement (eyes closed, camera recording)
    MEASUREMENT_SILENCE = auto()   # Silence between measurement beeps
    INSTRUCTION_POST = auto()      # Post-measurement MP3 (open eyes / next participant / completed)
    INTER_TRIAL = auto()           # Brief gap between shapes


class Shape(Enum):
    """Available stimulus shapes."""
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE = "triangle"
    STAR = "star"

    @classmethod
    def from_string(cls, name: str) -> "Shape":
        """Convert string to Shape enum (case-insensitive)."""
        return cls(name.lower())
