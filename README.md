# LSCI Visual Mental Imagery Experiment — Ver2

A research-grade experiment application for studying **Laser Speckle Contrast Imaging (LSCI)** responses during visual mental imagery tasks. The system presents geometric shapes with synchronized audio cues, records high-speed video of a subject's tissue via a Basler industrial camera, and manages multi-participant sessions with full data logging.

Built with **PyQt5** (operator GUI), **PsychoPy** (frame-accurate stimulus/audio), and **pypylon/OpenCV** (camera acquisition).

**Ver2** redesigns the measurement phase with discrete imagination cycles, each using distinct start/end beeps at different frequencies and individual per-cycle camera recordings.

---

## Table of Contents

- [Overview](#overview)
- [Experiment Protocol](#experiment-protocol)
- [Ver1 vs Ver2 Differences](#ver1-vs-ver2-differences)
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
2. **Imagine** the shape with eyes closed while discrete audio cues mark individual recording cycles (measurement phase)

A high-speed Basler camera captures tissue perfusion data during the measurement phase, producing a **separate video file for each imagination cycle**. The operator controls the session through a dedicated GUI window, separate from the participant's fullscreen stimulus display.

---

## Experiment Protocol

Each shape trial follows this sequence:

### Training Phase

The shape is presented N times (default 5). Each presentation:

| Step | Display | Audio |
|------|---------|-------|
| Shape appears **simultaneously** with start beep | White shape on black | 660 Hz tone (0.3s, vsync-synced) |
| Shape remains visible | Shape continues | Silence (beep ends during display) |
| Shape disappears **simultaneously** with end beep | Black screen | 880 Hz tone (0.5s, vsync-synced) |
| Blank gap | Black screen | Silence |

The start beep plays at the exact vsync moment the shape appears. The end beep plays at the exact vsync moment the shape disappears. Both are locked to the display refresh via `callOnFlip`.

### Instruction Sequence

| Phase | Description | Audio |
|-------|-------------|-------|
| **Close eyes** | MP3: *"Close your eyes and be ready to imagine the shape"* | MP3 playback |
| **5-second wait** | Participant prepares with eyes closed | Silence |
| **Starting** | MP3: *"Starting"* | MP3 playback |
| **2-second wait** | Final preparation before measurement | Silence |

### Measurement Phase (Per-Cycle Imagination)

Each imagination cycle (default 3 cycles) follows this sequence:

| Step | Display | Audio | Camera |
|------|---------|-------|--------|
| **Start beep** | Black screen | 660 Hz tone (0.3s) | Preview only |
| **Recording delay** (1.0s) | Black screen | Silence | Preview only |
| **Camera recording** | Black screen | Silence | **Recording** |
| **End beep** | Black screen | 880 Hz tone (0.5s) | Stopped |
| **Inter-cycle delay** (2.0s, skipped after last cycle) | Black screen | Silence | Preview only |

Each cycle produces its own AVI video file. The `imagination_duration` parameter defines the time from start beep onset to end beep onset; the actual recording duration is `imagination_duration - start_beep_duration - recording_delay`.

### Post-Measurement

Context-dependent MP3 instruction with 5-second wait:

- More shapes remaining in this turn: *"Open your eyes"*
- Last shape, more participants/reps remain: *"Next participant please"*
- Last shape of entire session: *"We have successfully completed the experiment"*

---

## Ver1 vs Ver2 Differences

| Aspect | Ver1 | Ver2 |
|--------|------|------|
| **Training beeps** | Single 440 Hz continuous tone during shape display | Distinct start (660 Hz) and end (880 Hz) beeps, simultaneous with shape appear/disappear |
| **Measurement beeps** | Continuous 440 Hz tone for N cycles with silence gaps | Discrete start (660 Hz) and end (880 Hz) beeps per cycle |
| **Camera recording** | One continuous recording across all measurement beeps | Separate recording per imagination cycle |
| **Video output** | Single AVI per shape trial | One AVI per imagination cycle (e.g., 3 cycles = 3 files) |
| **Recording start** | First beep onset | After start beep + configurable delay (default 1.0s) |
| **Configurable params** | `measurement_beep_duration`, `measurement_silence_duration`, `measurement_repetitions` | `imagination_duration`, `imagination_cycles`, `inter_imagination_delay`, `recording_delay`, `start_imagine_frequency/duration`, `end_imagine_frequency/duration` |

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
git clone https://github.com/Rotem-Aizenberg/-basler-mental-imagery-exp-ver2.git
cd basler-mental-imagery-exp-ver2
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
2. **Subjects** --- Add participant names (supports loading from previous sessions)
3. **Experiment Settings** --- Shapes, repetitions, timing, imagination parameters, output folder
4. **Camera Setup** --- Live preview, resolution, exposure, gain, frame rate
5. **Display & Audio** --- Select participant screen, select audio output device

### Operator Window

After the wizard, the main operator window displays:

- **Left panel:** Session queue showing all participant turns, with estimated end time
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
basler-mental-imagery-exp-ver2/
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

**Shapes:** `circle`, `square`, `triangle`, `star` (selectable in wizard). Custom images are also supported.

**Training Timing (in seconds):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `training_shape_duration` | 1.5 | Duration each shape is displayed (start beep plays at onset) |
| `training_blank_duration` | 0.5 | Silent gap after end beep before next repetition |
| `training_repetitions` | 5 | Number of shape presentations per training phase |
| `training_to_measurement_delay` | 0.0 | Extra delay between training and measurement phases |

**Imagination / Measurement Timing (in seconds):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `imagination_duration` | 10.0 | Time from start beep onset to end beep onset per cycle |
| `imagination_cycles` | 3 | Number of imagination cycles per shape trial |
| `inter_imagination_delay` | 2.0 | Gap between end beep offset and next start beep |
| `recording_delay` | 1.0 | Delay after start beep before camera starts recording |

**Audio:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `start_imagine_frequency` | 660.0 | Start beep frequency in Hz |
| `start_imagine_duration` | 0.3 | Start beep duration in seconds |
| `end_imagine_frequency` | 880.0 | End beep frequency in Hz |
| `end_imagine_duration` | 0.5 | End beep duration in seconds |

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
        |   |   |   |-- Alice_circle_rep1_shapeRep1_cycle1_20260214_143045.avi
        |   |   |   |-- Alice_circle_rep1_shapeRep1_cycle2_20260214_143055.avi
        |   |   |   +-- Alice_circle_rep1_shapeRep1_cycle3_20260214_143105.avi
        |   |   |-- square/
        |   |   |   |-- Alice_square_rep1_shapeRep1_cycle1_20260214_143200.avi
        |   |   |   |-- Alice_square_rep1_shapeRep1_cycle2_20260214_143210.avi
        |   |   |   +-- Alice_square_rep1_shapeRep1_cycle3_20260214_143220.avi
        |   |   +-- ...
        |   +-- rep_2/
        |       +-- ...
        +-- Bob/
            +-- rep_1/
                |-- circle/
                |   |-- Bob_circle_rep1_shapeRep1_cycle1_20260214_143400.avi
                |   +-- ...
                +-- ...
```

**Video files:** AVI format with MJPG codec. Each imagination cycle produces a separate file. Filename encodes subject, shape, repetition number, shape instance, cycle number, and timestamp.

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
- Training: shape appears and start beep triggers on the **same vsync flip**; shape disappears and end beep triggers on the **same vsync flip**
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
| psychopy | >= 2025.1.0 | Stimulus display and audio with frame-accurate timing |
| pypylon | >= 2.0 | Basler camera SDK bindings (Lab Mode only) |
| opencv-python | >= 4.5 | Video recording (MJPG/AVI) and webcam fallback |
| numpy | >= 1.21 | Array operations for frame and audio buffers |
| openpyxl | >= 3.0 | Excel file creation for data logging |
| sounddevice | >= 0.4 | Audio device enumeration and selection |
