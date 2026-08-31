# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PyQt5 desktop application for an LSCI (Laser Speckle Contrast Imaging) mental-imagery experiment. It presents shapes with beeps to a participant (via PsychoPy fullscreen window), records high-speed video of tissue with a Basler industrial camera (one AVI per imagination cycle), and gives the operator a control GUI. See README.md for the full experiment protocol, parameter tables, and output-directory layout.

## Running

```bash
python main.py              # normal launch (5-step setup wizard)
python main.py --dev-mode   # webcam instead of Basler; no pypylon/Pylon SDK needed
python main.py --config path/to/config.json
```

- Requires **Python 3.11.x** (PsychoPy does not support 3.12+). Lab Mode additionally requires the Basler Pylon SDK installed system-wide.
- There is no test suite, linter config, or build step. Verifying changes generally means launching with `--dev-mode` and exercising the wizard/experiment flow.
- Config defaults live in `config/defaults.json`, deserialized into the `ExperimentConfig` dataclass tree in `config/settings.py` (unknown JSON keys are silently dropped; missing keys fall back to dataclass defaults). Cross-session operator preferences persist in `.app_memory/memory.json`.

## Architecture

### Threading model — the most important constraint

- **GUI thread (PyQt5):** `gui/main_window.py`, panels, dialogs.
- **Engine thread (QThread):** `ExperimentEngine._run()` in `core/experiment_engine.py`. The PsychoPy `StimulusWindow`, `AudioManager`, and `TrialProtocol` are created **inside `_run()` on the engine thread** — the OpenGL context is thread-bound. Never create or touch PsychoPy objects from the GUI thread.
- **Camera thread:** each camera backend runs its own grab/record loop.

Communication: engine → GUI only via `pyqtSignal`s on `ExperimentWorker` (`utils/threading_utils.py`): `state_changed`, `phase_changed`, `beep_progress`, `stimulus_update`, `recording_started/saved/discarded`, etc. GUI → engine via `threading.Event`s on the engine (`_pause_event`, `_confirm_event`) and an `AtomicFlag` abort flag.

### Timing precision rules

All timing-critical code paths (in `core/trial_protocol.py`) use PsychoPy vsync frame counting, never sleep:

- Durations are frame counts: `for _ in range(n_frames): win.flip()`.
- Audio onset is vsync-locked via `win.callOnFlip(sound.play)` — shape appearance and start beep hit the same flip.
- Tone buffers are pre-generated at exactly `n_frames * frame_duration` seconds (`AudioManager.pregenerate_*` called from the engine after measuring the display's frame rate).
- Do not introduce `time.sleep()` into trial timing; `utils/timing.precise_sleep` exists only for non-vsync contexts.
- Per-cycle recording duration is derived: `imagination_duration − start_beep_duration − recording_delay` (in frames).

### Session flow

`SessionQueue` (`core/session_queue.py`) builds an interleaved queue: one `QueueItem` per subject×repetition (Rep 1: all subjects, Rep 2: all subjects, …), each item holding the full shape list (× `shape_reps_per_subsession`). The engine loop waits for operator "Confirm Next" (`_confirm_event`) before each item, then dispatches to `_run_block_item()` (one `TrialProtocol.run()` per shape) or, when `config.interleaving_mode` is set, `_run_interleaved_item()` (one `TrialProtocol.run_interleaved()` for the whole turn: observe MP3 → training for all shapes → close eyes → shuffled imagination cycles, each announced by an `imagine_<shape>` voice prompt). Interleaving mode requires an `Imagine a <shape>.mp3` per selected shape in `external_instruction_recordings/interleaving_mode/` — enforced by `ExperimentConfig.validate()`; it is incompatible with image stimuli.

**Pause/resume semantics:** Pause aborts the in-flight trial mid-cycle. Only the interrupted cycle's video is deleted (tracked via `saved_video_paths` vs `cycle_videos` in the engine loop); completed cycles are kept, and resume re-enters `TrialProtocol.run()` with `start_from_cycle = last_completed_cycle + 1`. Keep this per-cycle granularity when modifying retry logic.

Stop ends the session and closes the app; `ExperimentEngine.reset()` deliberately forces GC + a 0.5s delay to release OpenGL contexts (pyglet "Unable to share contexts" on Windows).

### Camera abstraction

`hardware/camera_base.py` defines the abstract `CameraBackend`; `camera_factory.py` picks `camera_basler.py` (pypylon, Lab Mode) or `camera_webcam.py` (OpenCV, Dev Mode). Code outside `hardware/` should only use the base interface so Dev Mode keeps working. Recording formats (MJPEG AVI default, uncompressed AVI, MP4) live in `hardware/video_formats.py` — both backends create writers via `create_video_writer()` (auto-fallback to MJPEG), `probe_format()` verifies a format with a real write on the current machine (uncompressed AVI is known to break on some OpenCV builds), and `SessionManager` derives file extensions from `config.camera.video_format`.

### Data outputs

`data/session_manager.py` owns the session directory layout and per-cycle video paths (filename encodes subject/shape/rep/shape-instance/cycle/timestamp). Three parallel logs: `event_logger.py` (ms-precision CSV of every event), `excel_logger.py` (one row per trial), `main_experiment_monitor.py` (cross-session `MAIN_experiment_monitoring.xlsx` in the output base dir). `progress.json` is a crash-recovery checkpoint written after each queue advance.

## Conventions

- Ver2 protocol specifics (distinct 660 Hz start / 880 Hz end beeps, per-cycle recordings) are what distinguish this repo from Ver1 — README's "Ver1 vs Ver2" table is the reference if protocol behavior changes.
- When changing protocol timing, beep parameters, or output structure, update the corresponding tables in README.md — it is the lab's operating document.
- Stimuli can be Shape enums (`core/enums.py`) or raw image-name strings (`"image_0"`, …) when `stimulus.use_images` is set; code touching queue items must handle both (see `shape.value if hasattr(shape, "value")` pattern).
