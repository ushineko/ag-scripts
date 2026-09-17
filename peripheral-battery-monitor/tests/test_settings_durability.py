"""Spec 027: settings survive a crash mid-save, and corruption is not silent.

The reported symptom was the bandwidth section "losing its config". The section
was fine; the settings file was being truncated to zero bytes at the start of
every save, and a file that failed to parse was silently replaced by defaults.

These tests drive the real load/save functions through an importlib-loaded copy
of the app module, because the file is named `peripheral-battery.py` and cannot
be imported normally.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

GOOD = {"bandwidth_interfaces": ["tailscale0", "eno2"], "opacity": 0.95}


def _load_app_module():
    """Import peripheral-battery.py under a legal module name."""
    path = os.path.join(PROJECT_DIR, "peripheral-battery.py")
    spec = importlib.util.spec_from_file_location("pbm_app", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pbm_app"] = module
    spec.loader.exec_module(module)
    return module


class _Harness:
    """Minimal stand-in exposing the real load/save bound to a temp path."""

    def __init__(self, module, directory):
        self.module = module
        self.dir = directory
        self.settings = {}
        module.CONFIG_PATH = os.path.join(directory, "settings.json")
        module.CONFIG_BACKUP_PATH = module.CONFIG_PATH + ".bak"
        module.CONFIG_CORRUPT_PATH = module.CONFIG_PATH + ".corrupt"
        cls = module.PeripheralMonitor
        self.load_settings = cls.load_settings.__get__(self)
        self.save_settings = cls.save_settings.__get__(self)
        self._read_settings_file = cls._read_settings_file

    @property
    def path(self):
        return self.module.CONFIG_PATH


class SettingsDurabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.module = _load_app_module()
        except Exception as e:                      # pragma: no cover
            raise unittest.SkipTest(f"app module not importable: {e}")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = _Harness(self.module, self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # -- normal operation ------------------------------------------------

    def test_round_trip(self):
        self.h.settings = dict(GOOD)
        self.h.save_settings()
        self.assertEqual(self.h.load_settings()["bandwidth_interfaces"],
                         ["tailscale0", "eno2"])

    def test_absent_file_is_silent_defaults(self):
        loaded = self.h.load_settings()
        self.assertEqual(loaded["bandwidth_interfaces"], [])
        self.assertFalse(os.path.exists(self.h.path + ".corrupt"))

    def test_save_leaves_no_temp_files(self):
        self.h.settings = dict(GOOD)
        self.h.save_settings()
        leftovers = [f for f in os.listdir(self.tmp.name) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    # -- the actual failure ----------------------------------------------

    def test_truncated_file_recovers_from_backup(self):
        """The reported bug: an empty file used to mean 'reset to defaults'."""
        self.h.settings = dict(GOOD)
        self.h.save_settings()                       # creates the file
        self.h.settings = dict(GOOD, opacity=0.5)
        self.h.save_settings()                       # now a backup exists too

        open(self.h.path, "w").close()               # crash mid-save: 0 bytes
        self.assertEqual(os.path.getsize(self.h.path), 0)

        loaded = self.h.load_settings()
        self.assertEqual(loaded["bandwidth_interfaces"], ["tailscale0", "eno2"],
                         "must recover the interfaces, not reset them")

    def test_truncated_file_without_backup_is_preserved_not_overwritten(self):
        with open(self.h.path, "w") as f:
            f.write('{"bandwidth_int')               # partial write
        loaded = self.h.load_settings()
        self.assertEqual(loaded["bandwidth_interfaces"], [])
        self.assertTrue(os.path.exists(self.h.path + ".corrupt"),
                        "the damaged file must be kept for inspection")

    def test_corrupt_file_is_not_silently_replaced(self):
        with open(self.h.path, "w") as f:
            f.write("not json at all")
        self.h.load_settings()
        with open(self.h.path + ".corrupt") as f:
            self.assertEqual(f.read(), "not json at all")

    def test_non_dict_json_is_treated_as_corrupt(self):
        with open(self.h.path, "w") as f:
            json.dump(["not", "a", "dict"], f)
        self.h.load_settings()
        self.assertTrue(os.path.exists(self.h.path + ".corrupt"))

    # -- a failed save must not destroy the good file --------------------

    def test_failed_save_leaves_the_existing_file_intact(self):
        self.h.settings = dict(GOOD)
        self.h.save_settings()
        before = open(self.h.path).read()

        class Unserialisable:
            pass

        self.h.settings = {"bad": Unserialisable()}
        self.h.save_settings()                       # must not raise
        self.assertEqual(open(self.h.path).read(), before,
                         "a failed save must not truncate the previous file")

    def test_backup_is_written_before_replace(self):
        self.h.settings = dict(GOOD)
        self.h.save_settings()
        self.h.settings = dict(GOOD, opacity=0.1)
        self.h.save_settings()
        with open(self.h.path + ".bak") as f:
            self.assertEqual(json.load(f)["opacity"], 0.95,
                             "backup should hold the PREVIOUS save")


if __name__ == "__main__":
    unittest.main()
