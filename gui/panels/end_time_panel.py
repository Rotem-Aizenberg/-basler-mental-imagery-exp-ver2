"""Seven-segment style expected end time display."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QLCDNumber


class EndTimePanel(QGroupBox):
    """Red seven-segment digital clock showing expected experiment end time.

    Displays time in HH:MM (24-hour) format using Qt's QLCDNumber widget
    for an authentic digital clock appearance.
    """

    def __init__(self, parent=None):
        super().__init__("Expected End Time", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 10, 6, 6)

        self._lcd = QLCDNumber(5)  # 5 digits: HH:MM
        self._lcd.setSegmentStyle(QLCDNumber.Flat)
        self._lcd.setFixedHeight(50)
        self._lcd.setStyleSheet(
            "background-color: #1A1A1A; "
            "color: #FF0000; "
            "border: 2px inset #333;"
        )
        # Set red digits via palette
        palette = self._lcd.palette()
        palette.setColor(QPalette.WindowText, QColor(255, 0, 0))
        palette.setColor(QPalette.Window, QColor(26, 26, 26))
        self._lcd.setPalette(palette)
        self._lcd.display("--:--")

        layout.addWidget(self._lcd)

        self._note_label = QLabel("")
        self._note_label.setAlignment(Qt.AlignCenter)
        self._note_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self._note_label)

        self.setLayout(layout)

    def set_time(self, hours: int, minutes: int) -> None:
        """Update the display with a specific time in 24h format."""
        self._lcd.display(f"{hours:02d}:{minutes:02d}")

    def set_note(self, text: str) -> None:
        """Set the small note text below the clock."""
        self._note_label.setText(text)

    def clear(self) -> None:
        """Reset to idle display."""
        self._lcd.display("--:--")
        self._note_label.setText("")
