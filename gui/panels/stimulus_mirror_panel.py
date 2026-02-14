"""Participant screen mirror panel for the operator window.

Renders a small preview of what's currently displayed on the participant's
screen, driven by the engine's stimulus_update signal.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QPolygonF
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class _MirrorCanvas(QWidget):
    """Custom widget that draws a mirror of the participant display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"
        self.setMinimumSize(200, 150)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Black background
        p.fillRect(0, 0, w, h, QColor(0, 0, 0))

        state = self._state

        if state.startswith("shape:"):
            shape_name = state.split(":")[1]
            self._draw_shape(p, shape_name, w, h)

        elif state == "blank":
            pass  # Already black

        elif state == "recording":
            # Red dot + text
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Segoe UI", 14, QFont.Bold))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "Recording...")
            p.setBrush(QColor(255, 0, 0))
            p.setPen(Qt.NoPen)
            p.drawEllipse(w // 2 - 60, h // 2 - 30, 12, 12)

        elif state.startswith("instruction:"):
            instruction = state.split(":")[1]
            text_map = {
                "close_eyes": "Close your eyes...",
                "starting": "Starting...",
                "open_your_eyes": "Open your eyes",
                "next_participant": "Next participant...",
                "experiment_completed": "Experiment completed!",
            }
            text = text_map.get(instruction, instruction)
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(0, 0, w, h, Qt.AlignCenter | Qt.TextWordWrap, text)

        elif state == "idle":
            p.setPen(QColor(128, 128, 128))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "Waiting...")

        else:
            p.setPen(QColor(128, 128, 128))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(0, 0, w, h, Qt.AlignCenter, state)

        p.end()

    def _draw_shape(self, p: QPainter, shape: str, w: int, h: int) -> None:
        """Draw a white shape on black background."""
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        cx, cy = w // 2, h // 2
        size = min(w, h) * 0.35

        if shape == "circle":
            p.drawEllipse(int(cx - size), int(cy - size),
                          int(size * 2), int(size * 2))

        elif shape == "square":
            p.drawRect(int(cx - size), int(cy - size),
                        int(size * 2), int(size * 2))

        elif shape == "triangle":
            points = QPolygonF()
            for i in range(3):
                angle = math.radians(90 + i * 120)
                x = cx + size * math.cos(angle)
                y = cy - size * math.sin(angle)  # Qt Y is flipped
                from PyQt5.QtCore import QPointF
                points.append(QPointF(x, y))
            p.drawPolygon(points)

        elif shape == "star":
            points = QPolygonF()
            outer = size
            inner = size * 0.4
            for i in range(10):
                angle = math.radians(90 + i * 36)
                r = outer if i % 2 == 0 else inner
                x = cx + r * math.cos(angle)
                y = cy - r * math.sin(angle)
                from PyQt5.QtCore import QPointF
                points.append(QPointF(x, y))
            p.drawPolygon(points)


class StimulusMirrorPanel(QGroupBox):
    """Panel that mirrors the participant screen in the operator window."""

    def __init__(self, parent=None):
        super().__init__("Participant Screen", parent)
        self._canvas = _MirrorCanvas()

        layout = QVBoxLayout()
        layout.addWidget(self._canvas)
        self.setLayout(layout)

    def update_state(self, state: str) -> None:
        """Update the mirror display.

        Called from the engine's stimulus_update signal.

        Args:
            state: e.g. "shape:circle", "blank", "recording",
                   "instruction:close_eyes", "idle"
        """
        self._canvas.set_state(state)
