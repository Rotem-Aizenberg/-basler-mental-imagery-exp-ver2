"""Pure-numpy waveform generation for experiment audio cues."""

from __future__ import annotations

import numpy as np


def generate_sine_tone(
    frequency: float,
    duration: float,
    sample_rate: int = 44100,
    volume: float = 0.5,
    fade_ms: float = 5.0,
) -> np.ndarray:
    """Generate a sine-wave tone as a float32 numpy array.

    Args:
        frequency: Tone frequency in Hz.
        duration: Duration in seconds.
        sample_rate: Audio sample rate.
        volume: Peak amplitude 0..1.
        fade_ms: Fade-in/out duration in milliseconds to avoid clicks.

    Returns:
        1-D float32 array of samples.
    """
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)
    wave = volume * np.sin(2 * np.pi * frequency * t)

    # Apply fade envelope to avoid clicks
    fade_samples = int(sample_rate * fade_ms / 1000)
    if fade_samples > 0 and n_samples > 2 * fade_samples:
        fade_in = np.linspace(0, 1, fade_samples, dtype=np.float32)
        fade_out = np.linspace(1, 0, fade_samples, dtype=np.float32)
        wave[:fade_samples] *= fade_in
        wave[-fade_samples:] *= fade_out

    return wave


def generate_silence(duration: float, sample_rate: int = 44100) -> np.ndarray:
    """Generate silence as a float32 numpy array."""
    return np.zeros(int(sample_rate * duration), dtype=np.float32)
