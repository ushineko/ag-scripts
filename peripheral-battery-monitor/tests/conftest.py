"""Test isolation for the settings file.

Several tests construct a real `PeripheralMonitor` with `load_settings` mocked
but `save_settings` live. `CONFIG_PATH` pointed at the user's actual
`~/.config/peripheral-battery-monitor.json`, so those tests wrote the mock's
two-key dict straight over the real configuration — every run of the suite wiped
it. That is what made a reported "bandwidth section keeps losing its config"
irreproducible by inspection: nothing in the app was wrong.

Redirecting by environment variable rather than by patching each call site means
a test added later cannot reintroduce the problem by forgetting to patch.
"""

import os
import tempfile

# Set before pytest imports any test module, so the app module computes
# CONFIG_PATH from it at import time.
_TMPDIR = tempfile.mkdtemp(prefix="pbm-test-config-")
os.environ["PBM_CONFIG_PATH"] = os.path.join(_TMPDIR, "settings.json")


def pytest_sessionfinish(session, exitstatus):
    import shutil
    shutil.rmtree(_TMPDIR, ignore_errors=True)
