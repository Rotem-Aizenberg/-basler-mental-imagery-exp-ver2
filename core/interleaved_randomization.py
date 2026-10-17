"""Uniform constrained randomization of complete interleaved cycle lists."""

from __future__ import annotations

import random
from collections import Counter
from typing import Callable, List, Optional, Sequence

MAX_CONSECUTIVE = 2
MAX_ATTEMPTS = 100_000


def generate_interleaved_sequence(
    shape_names: Sequence[str],
    cycles_per_shape: int,
    seed: int,
    *,
    should_abort: Optional[Callable[[], bool]] = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> List[str]:
    """Rejection-sample a balanced order with no three equal neighbours.

    Every proposal is a uniform shuffle of the full multiset. Each distinct
    class order has the same number of labelled permutations, so accepting
    only valid proposals samples uniformly from all valid class orders.
    No local repairs, forced alternation, or fallback ordering are used.

    Replaying with the same ordered inputs and seed reproduces the sequence.
    A bounded attempt count prevents very long rejection searches; exhaustion
    raises an error rather than returning a biased or invalid sequence.
    """
    if not shape_names or cycles_per_shape < 1:
        raise ValueError("Select at least one shape and one imagination cycle.")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive.")

    original = [name for name in shape_names for _ in range(cycles_per_shape)]
    largest_count = max(Counter(original).values())
    other_count = len(original) - largest_count
    if largest_count > MAX_CONSECUTIVE * (other_count + 1):
        raise ValueError(
            "Interleaving cannot avoid three consecutive recordings of the "
            "same shape with these counts. Select another shape or reduce "
            "the number of cycles or shape repetitions."
        )

    rng = random.Random(seed)
    for _ in range(max_attempts):
        if should_abort is not None and should_abort():
            raise InterruptedError("Interleaved randomization aborted.")
        candidate = original.copy()
        rng.shuffle(candidate)
        if all(candidate[i] != candidate[i - 1] or candidate[i] != candidate[i - 2]
               for i in range(2, len(candidate))):
            return candidate

    raise RuntimeError(
        f"Interleaved randomization found no valid sequence after "
        f"{max_attempts:,} attempts (seed={seed}). Reduce the imagination "
        "cycles or shape repetitions and try again. No sequence was started."
    )
