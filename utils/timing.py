"""High-precision timing utilities for Windows.

Windows time.sleep() has ~15ms granularity. For sub-ms timing needed
in the trial protocol, we use a hybrid approach: sleep for the bulk
then busy-wait spin for the final 2ms.
"""

from __future__ import annotations

import time

# Threshold below which we switch from sleep to busy-wait (seconds)
_SPIN_THRESHOLD = 0.002  # 2 ms


def precise_sleep(duration: float) -> None:
    """Sleep for *duration* seconds with sub-ms accuracy on Windows.

    Uses time.sleep() for the bulk of the wait, then a busy-wait
    spin loop for the final 2 ms to achieve high precision.
    """
    if duration <= 0:
        return

    target = time.perf_counter() + duration

    # Sleep for the bulk (minus spin threshold)
    sleep_duration = duration - _SPIN_THRESHOLD
    if sleep_duration > 0:
        time.sleep(sleep_duration)

    # Busy-wait spin for remaining time
    while time.perf_counter() < target:
        pass


def perf_timestamp() -> float:
    """Return a high-resolution monotonic timestamp (seconds)."""
    return time.perf_counter()
