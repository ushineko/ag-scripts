"""Audio Source Switcher package.

Re-exports for backward compatibility so that existing code doing:
    from audio_source_switcher import HeadsetController
continues to work after the module split.
"""

from audio_source_switcher.controllers.headset import HeadsetController  # noqa: F401
from audio_source_switcher.controllers.audio import AudioController  # noqa: F401
from audio_source_switcher.controllers.bluetooth import BluetoothController, ConnectThread  # noqa: F401
from audio_source_switcher.controllers.pipewire import PipeWireController, VolumeMonitorThread  # noqa: F401
from audio_source_switcher.config import ConfigManager  # noqa: F401
from audio_source_switcher.gui.main_window import MainWindow  # noqa: F401
