# LSI Visual Mental Imagery Experiment

A research-grade experiment application for studying **Laser Speckle Imaging (LSI)** responses during visual mental imagery tasks. The system presents geometric shapes with synchronized audio cues, records high-speed video of a subject's tissue via a Basler industrial camera, and manages multi-participant sessions with full data logging.

Built with **PyQt5** (operator GUI), **PsychoPy** (frame-accurate stimulus/audio), and **pypylon/OpenCV** (camera acquisition).

---

## Table of Contents

- [Overview](#overview)
- [Experiment Protocol](#experiment-protocol)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Output Data](#output-data)
- [Architecture](#architecture)
- [Development Mode](#development-mode)
- [Troubleshooting](#troubleshooting)
- [Dependencies](#dependencies)

---

## Overview

The experiment measures cerebral hemodynamic responses during mental imagery using LSCI. Participants undergo a structured protocol where they:

1. **Learn** a visual shape through repeated visual + auditory presentation (training phase)
2. **Imagine** the shape with eyes closed while audio cues mark recording intervals (measurement phase)

A high-speed Basler camera captures tissue perfusion data during the measurement phase. The operator controls the session through a dedicated GUI window, separate from the participant's fullscreen stimulus display.

---

## Experiment Protocol

Each shape trial follows this sequence:

| Phase | Description | Display | Audio | Camera |
|-------|-------------|---------|-------|--------|
| **Training** | Shape shown N times with synchronized beep | White shape on black | 440 Hz tone (vsync-synced) | Preview only |
| **Close eyes instruction** | MP3: *"Close your eyes and be ready to imagine the shape"* | Black screen | MP3 playback | Preview only |
| **5-second wait** | Participant prepares | Black screen | Silence | Preview only |
| **Starting instruction** | MP3: *"Starting"* | Black screen | MP3 playback | Preview only |
| **2-second wait** | Final preparation | Black screen | Silence | Preview only |
| **Measurement** | N beep cycles with silence gaps | Black screen | 440 Hz tone | **Recording** |
| **Post-measurement** | Context-dependent MP3 instruction | Black screen | MP3 playback | Stopped |

**Post-measurement instructions:**
- More shapes remaining in this turn: *"Open your eyes"* (5s delay before next shape)
- Last shape, more participants/reps remain: *"Next participant please"*
- Last shape of entire session: *"We have successfully completed the experiment"*

**Recording timing:** Camera starts recording at the onset of the first measurement beep and stops after a silence period (`measurement_silence_duration`) following the last beep offset.

---

## System Requirements

### Hardware
- **Camera:** Basler acA1440-220um USB3 (or compatible Basler USB3 camera)
- **USB:** USB 3.0 port (required for camera bandwidth)
- **Display:** Dual monitor setup recommended (operator + participant)
- **Audio:** Speakers or headphones for audio cue playback

### Software
- **OS:** Windows 10/11
- **Python:** 3.11.x (PsychoPy requires Python < 3.12)
- **Basler Pylon SDK:** Must be installed system-wide before pypylon ([download](https://www.baslerweb.com/en/downloads/software-downloads/))

---

## Installation

### 1. Install Prerequisites

- **Python 3.11.x** --- PsychoPy requires Python < 3.12. Install from [python.org](https://www.python.org/downloads/) or via `winget install Python.Python.3.11`
- **Basler Pylon SDK** --- Required for Lab Mode only; not needed for Dev Mode. Download from [baslerweb.com](https://www.baslerweb.com/en/downloads/software-downloads/)

### 2. Clone and Install

```bash
git clone https://github.com/Rotem-Aizenberg/basler-mental-imagery-exp.git
cd basler-mental-imagery-exp
pip install -r requirements.txt
```

### 3. Verify Camera (Lab Mode only)

```bash
python -c "from pypylon import pylon; tl=pylon.TlFactory.GetInstance(); print([d.GetModelName() for d in tl.EnumerateDevices()])"
```

This should print your Basler camera model name. Ensure the camera is connected to a USB 3.0 port and not in use by another application (e.g., Pylon Viewer).

---

## Usage

### Launch

```bash
# Standard launch (opens wizard)
python main.py

# Pre-select Dev Mode (webcam fallback, no Basler needed)
python main.py --dev-mode

# Use a custom configuration file
python main.py --config path/to/config.json
```

### Wizard Flow

On launch, a 5-step wizard guides the operator through setup:

1. **Mode Selection** --- Lab Mode (Basler camera) or Dev Mode (webcam fallback)
2. **Experiment Settings** --- Shapes, repetitions, timing parameters, output folder
3. **Camera Setup** --- Live preview, resolution, exposure, gain, frame rate
4. **Display & Audio** --- Select participant screen, select audio output device
5. **Subjects** --- Add participant names (supports loading from previous sessions)

### Operator Window

After the wizard, the main operator window displays:

- **Left panel:** Session queue showing all participant turns
- **Center panel:** Control buttons (Start / Pause / Resume / Stop), progress bars, and a stimulus mirror showing what the participant sees
- **Right panel:** Live camera preview

### Controls

| Button | Action |
|--------|--------|
| **Start** | Begin the experiment session |
| **Pause** | Immediately interrupt the current trial; recording is discarded. Press Resume to retry the same shape |
| **Resume** | Restart the interrupted shape trial |
| **Confirm Next** | Confirm readiness for the next participant's turn |
| **Stop** | End the session and close the program (confirmation required) |

### Stopping and Restarting

Pressing **Stop** ends the session and closes the application entirely. To start a new session, run `python main.py` again.

---

## Project Structure

```
basler-mental-imagery-exp/
|-- main.py                         # Entry point
|-- requirements.txt                # Python dependencies
|-- config/
|   |-- defaults.json               # Default experiment parameters
|   +-- settings.py                 # Dataclass configuration with JSON persistence
|-- core/
|   |-- enums.py                    # ExperimentState, TrialPhase, Shape enums
|   |-- experiment_engine.py        # Session orchestrator (runs on QThread)
|   |-- session_queue.py            # Interleaved participant x repetition queue
|   +-- trial_protocol.py           # Single-shape trial with frame-accurate timing
|-- hardware/
|   |-- camera_base.py              # Abstract camera interface
|   |-- camera_basler.py            # Basler pypylon implementation
|   |-- camera_webcam.py            # OpenCV webcam fallback (Dev Mode)
|   +-- camera_factory.py           # Camera backend factory
|-- audio/
|   |-- __init__.py                 # Audio device configuration
|   |-- audio_manager.py            # PsychoPy Sound playback + MP3 instructions
|   +-- tone_generator.py           # Sine wave buffer generation
|-- stimulus/
|   |-- shape_renderer.py           # PsychoPy shape stimulus creation
|   +-- stimulus_window.py          # Fullscreen PsychoPy window management
|-- data/
|   |-- app_memory.py               # Cross-session persistent preferences
|   |-- event_logger.py             # CSV event log with timestamps
|   |-- excel_logger.py             # Per-trial Excel log
|   |-- main_experiment_monitor.py  # Cross-session Excel monitoring log
|   +-- session_manager.py          # Session directory and file management
|-- gui/
|   |-- main_window.py              # Main operator window with wizard
|   |-- dialogs/
|   |   |-- mode_selector_dialog.py
|   |   |-- experiment_settings_dialog.py
|   |   |-- camera_setup_dialog.py
|   |   |-- display_audio_dialog.py
|   |   |-- subject_dialog.py
|   |   +-- completion_dialog.py
|   +-- panels/
|       |-- camera_preview_panel.py     # Live camera feed
|       |-- camera_settings_panel.py    # Camera parameter controls
|       |-- control_panel.py            # Dynamic experiment buttons
|       |-- progress_panel.py           # Dual progress bars
|       |-- queue_panel.py              # Session queue display
|       +-- stimulus_mirror_panel.py    # Operator-side stimulus preview
|-- utils/
|   |-- logging_setup.py            # Logging configuration
|   |-- threading_utils.py          # QThread worker with pyqtSignal
|   +-- timing.py                   # High-precision sleep utility
+-- external_instruction_recordings/
    |-- close_your_eyes.mp3
    |-- starting.mp3
    |-- Open_your_eyes.mp3
    |-- next_participant_please.mp3
    +-- We_have_successfully_completed.mp3
```

---

## Configuration

### defaults.json

The default configuration is stored in `config/defaults.json` and can be modified through the wizard GUI or by editing the file directly.

**Shapes:** `circle`, `square`, `triangle`, `star` (selectable in wizard)

**Timing (in seconds):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `training_shape_duration` | 1.5 | Duration each shape is displayed with beep |
| `training_blank_duration` | 0.5 | Silent gap between training flashes |
| `training_repetitions` | 5 | Number of shape+beep presentations per training phase |
| `measurement_beep_duration` | 1.5 | Duration of each measurement beep |
| `measurement_silence_duration` | 0.5 | Silent gap between measurement beeps |
| `measurement_repetitions` | 5 | Number of beep cycles during measurement |

**Camera:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `width` / `height` | 128 x 128 | Sensor ROI dimensions (pixels) |
| `pixel_format` | Mono8 | 8-bit grayscale |
| `exposure_time_us` | 1000.0 | Sensor exposure time (microseconds) |
| `gain_db` | 17.7 | Signal amplification (dB) |
| `target_frame_rate` | 500.0 | Acquisition speed (fps) |

**Session:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `repetitions` | 5 | Number of complete rounds per subject |
| `shape_reps_per_subsession` | 1 | Times each shape repeats within one turn before moving to next participant |

### Persistent Memory

The application stores cross-session preferences in `.app_memory/memory.json` (auto-created in the project directory):
- Last used output folder
- Subject name history (for quick reload)
- Last experiment settings
- Last audio device and screen selection

---

## Output Data

Each session creates a timestamped directory under the configured output folder:

```
output_base_dir/
|-- MAIN_experiment_monitoring.xlsx              # Cross-session monitoring log
+-- session_YYYY-MM-DD_HH-MM-SS/
    |-- event_log.csv                            # Timestamped event log (ms precision)
    |-- session_log.xlsx                         # Per-trial Excel summary
    |-- session_config.json                      # Configuration snapshot
    |-- progress.json                            # Crash-recovery checkpoint
    +-- subjects/
        |-- Alice/
        |   |-- rep_1/
        |   |   |-- circle/
        |   |   |   +-- Alice_circle_rep1_shapeRep1_20260214_143045.avi
        |   |   |-- square/
        |   |   |   +-- Alice_square_rep1_shapeRep1_20260214_143112.avi
        |   |   +-- ...
        |   +-- rep_2/
        |       +-- ...
        +-- Bob/
            +-- rep_1/
                |-- circle/
                |   +-- Bob_circle_rep1_shapeRep1_20260214_143230.avi
                +-- ...
```

**Video files:** AVI format with MJPG codec. Filename encodes subject, shape, repetition number, shape instance, and timestamp.

**Event log:** CSV with millisecond-precision timestamps for every experimental event (trial start/end, beep on/off, recording start/stop, instructions).

**Session log:** Excel workbook with one row per trial summarizing subject, shape, repetition, status, and video filename.

**Main Experiment Monitor:** `MAIN_experiment_monitoring.xlsx` is created/appended in the output base directory, logging every session with date, time, participants, shapes, repetitions, camera settings, and completion status.

---

## Architecture

### Threading Model

```
GUI Thread (PyQt5)              Engine Thread (QThread)
+------------------+           +-------------------------+
|  MainWindow      |           |  ExperimentEngine._run() |
|  ControlPanel    |  signals  |  |-- StimulusWindow      |
|  ProgressPanel   | <-------- |  |-- AudioManager        |
|  QueuePanel      |           |  +-- TrialProtocol       |
|  StimulusMirror  |           |                           |
|  CameraPreview   |           |  Camera Record Thread     |
+------------------+           +-------------------------+
```

- **PsychoPy Window + Audio** are created on the engine thread (OpenGL context is thread-bound)
- **pyqtSignal** bridges engine thread to GUI thread for state changes, progress updates, and stimulus mirror
- **threading.Event** provides pause/confirm blocking between operator and engine
- **Camera** runs its own recording thread with continuous preview grab loop

### Timing Precision

All timing-critical operations use PsychoPy's vsync-locked frame counting:

- `win.callOnFlip(audio.play)` --- audio onset synchronized to exact display refresh
- `for _ in range(n_frames): win.flip()` --- durations determined by display refresh rate, not sleep
- Tone buffers pre-generated at `n_frames * frame_duration` for sample-accurate duration matching
- No `time.sleep()` in any timing-critical code path

---

## Development Mode

Dev Mode allows running the full experiment workflow without Basler hardware:

```bash
python main.py --dev-mode
```

**Differences from Lab Mode:**

| Aspect | Lab Mode | Dev Mode |
|--------|----------|----------|
| Camera | Basler acA1440-220um via pypylon | System webcam via OpenCV |
| Frame rate | Configured (default 500 fps) | Webcam native (typically 30 fps) |
| Frame rate measurement | Manual vsync measurement | Skipped (assumes 60 Hz) |
| pypylon required | Yes | No |
| Recording format | AVI (MJPG) | AVI (MJPG) |

All other functionality (wizard, stimulus timing, audio, data logging, progress tracking) works identically in both modes.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `pypylon` import error | Install Basler Pylon SDK first, then `pip install pypylon` |
| No Basler camera detected | Check USB 3.0 connection; close Pylon Viewer if open |
| PsychoPy import error | Ensure Python 3.11.x (not 3.12+); reinstall with `pip install psychopy` |
| Audio plays through wrong device | Select the correct speaker in the Display & Audio wizard step |
| "Get ready" text stays on screen | Frame rate measurement is running; wait a few seconds for it to complete |
| Webcam not available in Dev Mode | Check that no other application is using the webcam |
| Permission errors on output folder | Choose a folder with write access in the Experiment Settings wizard step |
| Application won't start after crash | Delete `.app_memory/memory.json` to reset saved preferences |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt5 | >= 5.15 | Operator GUI framework |
| psychopy | >= 2024.1.0 | Stimulus display and audio with frame-accurate timing |
| pypylon | >= 2.0 | Basler camera SDK bindings (Lab Mode only) |
| opencv-python | >= 4.5 | Video recording (MJPG/AVI) and webcam fallback |
| numpy | >= 1.21 | Array operations for frame and audio buffers |
| openpyxl | >= 3.0 | Excel file creation for data logging |
| sounddevice | >= 0.4 | Audio device enumeration and selection |
