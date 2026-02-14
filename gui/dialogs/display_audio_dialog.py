"""Display and audio device selection dialog."""

from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QApplication,
)

from data.app_memory import AppMemory

logger = logging.getLogger(__name__)


class DisplayAudioDialog(QDialog):
    """Wizard step 4: select display screen and audio output device."""

    def __init__(self, memory: AppMemory, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Display & Audio")
        self.setMinimumWidth(500)
        self._memory = memory
        self._selected_screen = 0
        self._selected_device = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Screen selection
        screen_group = QGroupBox("Stimulus Display")
        screen_layout = QVBoxLayout()

        self._screen_combo = QComboBox()
        app = QApplication.instance()
        screens = app.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            primary = " (Primary)" if screen == app.primaryScreen() else ""
            self._screen_combo.addItem(
                f"Screen {i + 1}: {screen.name()} "
                f"({geo.width()}x{geo.height()}){primary}",
                i,
            )
        # Default to last screen (likely secondary) or saved preference
        if self._memory.last_screen_index >= 0 and self._memory.last_screen_index < len(screens):
            self._screen_combo.setCurrentIndex(self._memory.last_screen_index)
        elif len(screens) > 1:
            self._screen_combo.setCurrentIndex(len(screens) - 1)

        screen_layout.addWidget(self._screen_combo)

        test_screen_btn = QPushButton("Test Screen")
        test_screen_btn.setToolTip("Briefly flash white on the selected screen")
        test_screen_btn.clicked.connect(self._test_screen)
        screen_layout.addWidget(test_screen_btn)

        screen_group.setLayout(screen_layout)
        layout.addWidget(screen_group)

        # Speaker selection
        speaker_group = QGroupBox("Audio Output")
        speaker_layout = QVBoxLayout()

        self._speaker_combo = QComboBox()
        self._populate_speakers()
        speaker_layout.addWidget(self._speaker_combo)

        test_speaker_btn = QPushButton("Test Speaker")
        test_speaker_btn.setToolTip("Play a short beep through the selected speaker")
        test_speaker_btn.clicked.connect(self._test_speaker)
        speaker_layout.addWidget(test_speaker_btn)

        speaker_group.setLayout(speaker_layout)
        layout.addWidget(speaker_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        next_btn = QPushButton("Next")
        next_btn.setStyleSheet("font-weight: bold; padding: 8px 20px;")
        next_btn.clicked.connect(self._on_next)
        btn_layout.addWidget(next_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _populate_speakers(self) -> None:
        """Fill the speaker combo with available output devices."""
        self._speaker_combo.addItem("System Default", "")
        try:
            from audio import list_audio_devices
            devices = list_audio_devices()
            for name in devices:
                self._speaker_combo.addItem(name, name)
            # Restore last used device
            if self._memory.last_audio_device:
                idx = self._speaker_combo.findData(self._memory.last_audio_device)
                if idx >= 0:
                    self._speaker_combo.setCurrentIndex(idx)
        except Exception as e:
            logger.warning("Could not list audio devices: %s", e)

    def _test_screen(self) -> None:
        """Briefly flash white on the selected screen."""
        screen_idx = self._screen_combo.currentData()
        try:
            app = QApplication.instance()
            screens = app.screens()
            if screen_idx < len(screens):
                screen = screens[screen_idx]
                geo = screen.geometry()

                from PyQt5.QtWidgets import QWidget
                from PyQt5.QtCore import QTimer

                # Keep reference so widget isn't garbage collected
                self._flash_widget = QWidget()
                self._flash_widget.setWindowFlags(
                    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                )
                self._flash_widget.setStyleSheet("background-color: white;")
                self._flash_widget.setGeometry(geo)
                self._flash_widget.showFullScreen()
                self._flash_widget.raise_()
                self._flash_widget.activateWindow()

                def _close_flash():
                    if hasattr(self, '_flash_widget') and self._flash_widget:
                        self._flash_widget.close()
                        self._flash_widget = None

                QTimer.singleShot(800, _close_flash)
        except Exception as e:
            logger.warning("Screen test failed: %s", e)

    def _test_speaker(self) -> None:
        """Play a short beep through the selected speaker."""
        device_name = self._speaker_combo.currentData()
        try:
            from audio import configure_audio
            configure_audio(device_name or "")
            from audio.audio_manager import AudioManager
            from config.settings import AudioSettings
            mgr = AudioManager(AudioSettings())
            mgr.test_output()
        except Exception as e:
            logger.warning("Speaker test failed: %s", e)

    def _on_next(self) -> None:
        self._selected_screen = self._screen_combo.currentData()
        self._selected_device = self._speaker_combo.currentData() or ""
        # Save to memory
        self._memory.last_screen_index = self._selected_screen
        self._memory.last_audio_device = self._selected_device
        self._memory.save()
        self.accept()

    @property
    def selected_screen(self) -> int:
        return self._selected_screen

    @property
    def selected_audio_device(self) -> str:
        return self._selected_device
