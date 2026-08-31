#!/usr/bin/env python3
"""LSCI Visual Mental Imagery Experiment — Entry Point.

Usage:
    python main.py                  # Launch with wizard
    python main.py --dev-mode       # Pre-select dev mode
    python main.py --config path    # Custom config file
    python main.py --check-setup    # Verify Python/dependencies and exit

Works with ANY Python on the PATH: if started with an unsupported
Python version (PsychoPy needs 3.8–3.11), it automatically finds a
compatible interpreter on the machine and relaunches itself with it.
Missing dependencies are reported with the exact install command —
in a popup window too, so double-clicking main.py never fails silently.
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

# Ensure the package root is on sys.path so relative imports work
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PsychoPy supports Python 3.8 – 3.11
_MIN_PY = (3, 8)
_MAX_PY_EXCL = (3, 12)
_BOOTSTRAP_ENV = "LSCI_BOOTSTRAPPED"

# module name -> pip package name
_REQUIRED = {
    "PyQt5": "PyQt5",
    "numpy": "numpy",
    "cv2": "opencv-python",
    "openpyxl": "openpyxl",
    "psychopy": "psychopy",
    "sounddevice": "sounddevice",
}


def _show_error(title: str, message: str) -> None:
    """Print an error and, on Windows, also show a message box so the
    problem is visible even when main.py was double-clicked (no console)."""
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}\n{message}\n", file=sys.stderr)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
        except Exception:
            pass


def _version_ok(vi=None) -> bool:
    vi = vi or sys.version_info
    return _MIN_PY <= (vi[0], vi[1]) < _MAX_PY_EXCL


def _find_compatible_python() -> "list[str] | None":
    """Find a Python 3.8–3.11 interpreter on this machine."""
    probe = (
        "import sys;"
        f"sys.exit(0 if {_MIN_PY} <= sys.version_info[:2] < {_MAX_PY_EXCL} else 1)"
    )
    candidates: "list[list[str]]" = [
        ["py", "-3.11"], ["py", "-3.10"], ["py", "-3.9"], ["py", "-3.8"],
        ["python3.11"], ["python3.10"],
    ]
    local = os.environ.get("LOCALAPPDATA", "")
    for ver in ("311", "310", "39", "38"):
        for base in (
            Path(local) / "Programs" / "Python" / f"Python{ver}" / "python.exe",
            Path(f"C:/Python{ver}/python.exe"),
            Path(f"C:/Program Files/Python{ver}/python.exe"),
        ):
            if base.exists():
                candidates.append([str(base)])

    for cand in candidates:
        try:
            r = subprocess.run(
                cand + ["-c", probe],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0:
                return cand
        except Exception:
            continue
    return None


def _ensure_python_version() -> None:
    """Relaunch with a compatible interpreter if this one is unsupported."""
    if _version_ok():
        return

    this_ver = f"{sys.version_info[0]}.{sys.version_info[1]}"

    if os.environ.get(_BOOTSTRAP_ENV) == "1":
        # Already relaunched once — don't loop
        _show_error(
            "LSCI Experiment — Python version error",
            f"Relaunch ended up on unsupported Python {this_ver}.\n"
            f"PsychoPy requires Python {_MIN_PY[0]}.{_MIN_PY[1]}–3.11.\n\n"
            "Install Python 3.11 from https://www.python.org/downloads/\n"
            "then run:  py -3.11 main.py",
        )
        sys.exit(1)

    compatible = _find_compatible_python()
    if compatible:
        print(
            f"Python {this_ver} is not supported by PsychoPy — "
            f"relaunching with: {' '.join(compatible)}",
        )
        env = dict(os.environ, **{_BOOTSTRAP_ENV: "1"})
        try:
            ret = subprocess.call(
                compatible + [str(_ROOT / "main.py")] + sys.argv[1:], env=env,
            )
            sys.exit(ret)
        except Exception as e:
            _show_error(
                "LSCI Experiment — launch error",
                f"Failed to relaunch with {' '.join(compatible)}:\n{e}",
            )
            sys.exit(1)

    _show_error(
        "LSCI Experiment — Python version error",
        f"This app needs Python {_MIN_PY[0]}.{_MIN_PY[1]}–3.11 "
        f"(PsychoPy limitation), but it was started with Python {this_ver} "
        "and no compatible Python was found on this PC.\n\n"
        "Install Python 3.11 from https://www.python.org/downloads/\n"
        "(check 'Add python.exe to PATH' in the installer), then run:\n\n"
        "    py -3.11 -m pip install -r requirements.txt\n"
        "    py -3.11 main.py",
    )
    sys.exit(1)


def _ensure_dependencies() -> None:
    """Verify required packages are importable; report ALL missing at once."""
    missing = [pip for mod, pip in _REQUIRED.items() if find_spec(mod) is None]
    if not missing:
        return
    exe = sys.executable
    _show_error(
        "LSCI Experiment — missing packages",
        "The following required packages are not installed for\n"
        f"{exe}:\n\n    " + ", ".join(missing) + "\n\n"
        "Install them by running:\n\n"
        f'    "{exe}" -m pip install -r requirements.txt\n\n'
        f"(from the folder: {_ROOT})",
    )
    sys.exit(1)


def _check_setup_report() -> None:
    """Print a setup diagnosis (--check-setup) and exit."""
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    for mod, pip in _REQUIRED.items():
        spec = find_spec(mod)
        print(f"  {pip:<15} {'OK' if spec else 'MISSING'}")
    pylon = find_spec("pypylon")
    print(f"  {'pypylon':<15} {'OK' if pylon else 'not installed (Dev Mode only)'}")
    print("Setup OK — ready to run: python main.py")
    sys.exit(0)


def main() -> None:
    _ensure_python_version()
    _ensure_dependencies()

    if "--check-setup" in sys.argv:
        _check_setup_report()

    import argparse

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

    from PyQt5.QtWidgets import QApplication

    from config.settings import ExperimentConfig
    from utils.logging_setup import setup_logging
    from gui.main_window import MainWindow

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
