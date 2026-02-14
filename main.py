#!/usr/bin/env python3
"""LSCI Visual Mental Imagery Experiment — Entry Point.

Usage:
    python main.py                  # Launch with wizard
    python main.py --dev-mode       # Pre-select dev mode
    python main.py --config path    # Custom config file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the package root is on sys.path so relative imports work
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt5.QtWidgets import QApplication

from config.settings import ExperimentConfig
from utils.logging_setup import setup_logging
from gui.main_window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LSCI Visual Mental Imagery Experiment",
    )
    parser.add_argument(
        "--dev-mode",
        action="store_true",
        help="Pre-select dev mode (webcam fallback)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a custom config JSON file",
    )
    args = parser.parse_args()

    # Load config
    defaults_path = _ROOT / "config" / "defaults.json"
    if args.config:
        config = ExperimentConfig.load(Path(args.config))
    elif defaults_path.exists():
        config = ExperimentConfig.load(defaults_path)
    else:
        config = ExperimentConfig()

    if args.dev_mode:
        config.dev_mode = True

    # Setup logging (console only until session starts)
    setup_logging()

    # Launch application
    app = QApplication(sys.argv)
    app.setApplicationName("LSCI Experiment")
    app.setStyle("Fusion")

    window = MainWindow(config)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
