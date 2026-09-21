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
        self._drop_retired = cls._drop_retired.__get__(self)
        self._retired_dropped = False

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

    # -- keys the lighting left behind (spec 039) -------------------------

    def test_retired_keys_are_dropped_on_load(self):
        """A settings file that still lists a scene bank and an LCD interval
        describes a program that no longer exists. Nothing reads them."""
        self.h.settings = {**GOOD, "aio_scenes": {"1": {"color": "red"}},
                           "aio_lcd_dashboard": True,
                           "lighting_last_color": "purple",
                           "keyboard_effect": "splash"}
        self.h.save_settings()

        loaded = self.h.load_settings()
        for key in ("aio_scenes", "aio_lcd_dashboard", "lighting_last_color",
                    "keyboard_effect"):
            self.assertNotIn(key, loaded)

    def test_dropping_them_keeps_everything_else(self):
        """The whole risk of a removal like this: taking a live key with it."""
        self.h.settings = {**GOOD, "aio_scenes": {}, "lighting_scope": ["kraken"]}
        self.h.save_settings()

        loaded = self.h.load_settings()
        self.assertEqual(loaded["bandwidth_interfaces"], ["tailscale0", "eno2"])
        self.assertIn("aio_section_enabled", loaded)

    def test_loading_says_whether_anything_was_dropped(self):
        """The flag the startup path saves on. Without it the cleaned file is
        only written when the user happens to change something else, which on
        a widget that is mostly looked at rather than used is close to never.
        """
        self.h.settings = {**GOOD, "aio_scenes": {"1": {"color": "red"}}}
        self.h.save_settings()

        self.h.load_settings()
        self.assertTrue(self.h._retired_dropped)

    def test_a_clean_file_triggers_no_save(self):
        """And a file with none of them left alone: a start that rewrites the
        settings for no reason is a start that can lose them for no reason."""
        self.h.settings = dict(GOOD)
        self.h.save_settings()

        self.h.load_settings()
        self.assertFalse(self.h._retired_dropped)

    def test_they_leave_the_file_on_the_next_save(self):
        """Dropped on load, written out on save."""
        self.h.settings = {**GOOD, "aio_scenes": {"1": {"color": "red"}}}
        self.h.save_settings()

        self.h.settings = self.h.load_settings()
        self.h.save_settings()

        with open(self.h.path) as f:
            self.assertNotIn("aio_scenes", json.load(f))

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
