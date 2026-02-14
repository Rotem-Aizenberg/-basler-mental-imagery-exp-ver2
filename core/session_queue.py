"""Interleaved subject x repetition queue builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .enums import Shape


@dataclass
class QueueItem:
    """One entry in the session queue: a subject's full shape set for one rep."""
    subject: str
    rep: int
    shapes: List[Shape] = field(default_factory=list)
    completed: bool = False

    @property
    def label(self) -> str:
        return f"{self.subject} - Rep {self.rep}"


class SessionQueue:
    """Builds and manages the interleaved experiment queue.

    The queue interleaves subjects within each repetition:
        Rep 1: Subject A, Subject B, Subject C
        Rep 2: Subject A, Subject B, Subject C
        ...
    Each queue item contains all shapes for that subject+rep,
    optionally repeated ``shape_reps_per_subsession`` times.
    """

    def __init__(
        self,
        subjects: List[str],
        repetitions: int,
        shapes: List[str],
        shape_reps_per_subsession: int = 1,
    ):
        self._items: List[QueueItem] = []
        shape_enums = [Shape.from_string(s) for s in shapes]

        # Build the shape list: shapes * shape_reps_per_subsession
        expanded_shapes = list(shape_enums) * shape_reps_per_subsession

        for rep in range(1, repetitions + 1):
            for subj in subjects:
                self._items.append(QueueItem(
                    subject=subj,
                    rep=rep,
                    shapes=list(expanded_shapes),
                ))

        self._index = 0

    @property
    def items(self) -> List[QueueItem]:
        return list(self._items)

    @property
    def current(self) -> QueueItem | None:
        if self._index < len(self._items):
            return self._items[self._index]
        return None

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def total(self) -> int:
        return len(self._items)

    @property
    def is_done(self) -> bool:
        return self._index >= len(self._items)

    def advance(self) -> QueueItem | None:
        """Mark current item completed and move to next. Returns new current or None."""
        if self._index < len(self._items):
            self._items[self._index].completed = True
            self._index += 1
        return self.current

    def reset_current(self) -> None:
        """Reset the current item for retry."""
        if self._index < len(self._items):
            self._items[self._index].completed = False

    def to_progress_dict(self) -> dict:
        """Serialize queue state for crash recovery."""
        return {
            "index": self._index,
            "items": [
                {
                    "subject": item.subject,
                    "rep": item.rep,
                    "completed": item.completed,
                }
                for item in self._items
            ],
        }
