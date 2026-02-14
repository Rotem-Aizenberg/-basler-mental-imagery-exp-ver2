"""Audio package — configures PsychoPy audio backend before first import.

IMPORTANT: This module MUST be imported before any ``psychopy.sound``
import anywhere in the codebase.  The preference must be set before
PsychoPy initialises its audio subsystem.
"""

_configured_device = None


def configure_audio(device_name: str = "") -> None:
    """Set up PsychoPy audio preferences.

    Args:
        device_name: Specific audio output device name. Empty string
            for system default.
    """
    global _configured_device
    try:
        from psychopy import prefs
        prefs.hardware['audioLib'] = ['ptb', 'sounddevice', 'pygame']
        prefs.hardware['audioLatencyMode'] = 3  # aggressive low-latency

        if device_name:
            prefs.hardware['audioDevice'] = [device_name]
            _configured_device = device_name
        else:
            # PTB's default resolution maps to legacy Windows names like
            # "Microsoft Sound Mapper - Output" which PTB itself can't find.
            # Use sounddevice to detect a real device name, skipping legacy
            # virtual devices that only exist in the MME API.
            _LEGACY = {"Microsoft Sound Mapper", "Primary Sound Driver"}
            try:
                import sounddevice as sd
                # Try the system default first
                default_idx = sd.default.device[1]
                if default_idx >= 0:
                    name = sd.query_devices(default_idx)['name']
                    if not any(leg in name for leg in _LEGACY):
                        prefs.hardware['audioDevice'] = [name]
                        _configured_device = name
                        return
                # Default is a legacy device — find first real output device
                for d in sd.query_devices():
                    if d['max_output_channels'] > 0:
                        if not any(leg in d['name'] for leg in _LEGACY):
                            prefs.hardware['audioDevice'] = [d['name']]
                            _configured_device = d['name']
                            return
            except Exception:
                pass
    except ImportError:
        pass


def list_audio_devices():
    """Return list of available audio output device names.

    Filters out legacy Windows virtual devices (MME Sound Mapper etc.)
    that PTB cannot use.
    """
    _LEGACY = {"Microsoft Sound Mapper", "Primary Sound Driver"}
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        output_devices = []
        seen = set()
        for d in devices:
            if d['max_output_channels'] > 0:
                name = d['name']
                if name not in seen and not any(leg in name for leg in _LEGACY):
                    output_devices.append(name)
                    seen.add(name)
        return output_devices
    except Exception:
        return []


# Auto-configure on import with system default
configure_audio()
