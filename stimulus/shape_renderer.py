"""PsychoPy visual stimuli factory for experiment shapes.

Creates pre-built PsychoPy stimulus objects (Circle, Rect, ShapeStim)
that can be drawn with a single ``stim.draw()`` call — no allocation
during the frame loop.
"""

from __future__ import annotations

import math

from core.enums import Shape


def create_shape_stim(win, shape: Shape, size: float = 0.5, color: str = "white"):
    """Create a PsychoPy visual stimulus for the given shape.

    Args:
        win: PsychoPy ``visual.Window`` instance.
        shape: Which shape to create.
        size: Shape size in ``height`` units (fraction of window height).
        color: Fill and line colour name.

    Returns:
        A PsychoPy stimulus object with a ``.draw()`` method.
    """
    from psychopy import visual

    if shape == Shape.CIRCLE:
        return visual.Circle(
            win, radius=size / 2,
            fillColor=color, lineColor=color,
            units="height",
        )

    elif shape == Shape.SQUARE:
        return visual.Rect(
            win, width=size, height=size,
            fillColor=color, lineColor=color,
            units="height",
        )

    elif shape == Shape.TRIANGLE:
        r = size / 2
        vertices = []
        for i in range(3):
            angle = math.radians(90 + i * 120)
            vertices.append((r * math.cos(angle), r * math.sin(angle)))
        return visual.ShapeStim(
            win, vertices=vertices,
            fillColor=color, lineColor=color,
            units="height",
        )

    elif shape == Shape.STAR:
        outer = size / 2
        inner = outer * 0.4
        vertices = []
        for i in range(10):
            angle = math.radians(90 + i * 36)
            r = outer if i % 2 == 0 else inner
            vertices.append((r * math.cos(angle), r * math.sin(angle)))
        return visual.ShapeStim(
            win, vertices=vertices,
            fillColor=color, lineColor=color,
            units="height",
        )

    else:
        raise ValueError(f"Unknown shape: {shape}")
